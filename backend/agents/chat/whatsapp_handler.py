"""
TatvaOps – WhatsApp Webhook Handler (Twilio)
EVA routing + specialized consultants + media uploads.
"""
from __future__ import annotations
import asyncio
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, Request, Response, BackgroundTasks

from backend.config import get_settings
from backend.schemas.session import Session, ConversationStage, MessageRole
from backend.intelligence.conversation_controller import get_controller
from backend.intelligence import hybrid_flow
from backend.intelligence import edit_flow
from backend.intelligence import stage_engine as se
from backend.intelligence.nova_router import get_service_selection_outbound_step
from backend.intelligence.qualification_builder import get_final_review_outbound_step
from backend.storage.redis_store import get_session, save_session
from backend.storage import supabase_store
from backend.storage.media_store import save_attachment
from backend.agents.chat.twilio_client import (
    enrich_whatsapp_mcq_step,
    send_context_then_mcq_list,
    send_whatsapp_message,
    send_whatsapp_flow,
    twiml_response,
)
from backend.agents.chat.whatsapp_interactive import build_inbound_user_message, parse_list_selection_id
from backend.utils.logger import log_event
from backend.utils.session_idle import (
    is_session_idle_expired,
    is_greeting_message,
    had_conversation_progress,
    build_idle_fresh_start_reply,
    start_fresh_session,
)
from backend.integrations.tatva_users import register_tatva_user_for_session, VENDOR_BLOCKED_MESSAGE

router = APIRouter()
_settings = get_settings()


def _normalize_restart_command(message: str) -> str:
    return (message or "").strip().upper().replace(" ", "")


def _normalize_user_text(message: str) -> str:
    return (message or "").strip().upper().replace(" ", "")


def _is_restart_command(message: str) -> bool:
    return _normalize_restart_command(message) == "RESTART45"


def _is_post_submit_polite_reply(message: str) -> bool:
    """Thanks / OK after submit — do not start a new qualification flow."""
    norm = _normalize_user_text(message)
    if not norm:
        return False
    polite_prefixes = ("THANK", "THX", "TY", "OK", "OKAY", "GOTIT", "CHEERS", "COOL")
    return any(norm.startswith(p) for p in polite_prefixes)


def _is_new_enquiry_intent(message: str) -> bool:
    """Explicit signal to start a fresh enquiry after a previous submit."""
    return is_greeting_message(message)


def _session_is_submitted(session: Session) -> bool:
    return bool(
        session.summary_generated
        or session.conversation_stage == ConversationStage.SUMMARY_GENERATED
    )


async def _handle_restart45(session_id: str, phone_number: str) -> str:
    """Clear session and return EVA welcome."""
    await start_fresh_session(session_id, phone_number, reason="RESTART45")
    session = await get_session(session_id)
    intro = hybrid_flow.first_client_message()
    if session:
        session.add_message(MessageRole.ASSISTANT, intro)
        se.start_client_stage(session)
        await save_session(session)
    return "Session reset.\n\n" + intro


def _twilio_validation_url(request: Request) -> str:
    """URL Twilio signed — must match the webhook URL in Console (incl. query string)."""
    url = f"{_settings.base_url.rstrip('/')}{request.scope['path']}"
    if request.url.query:
        url = f"{url}?{request.url.query}"
    return url


def _validate_twilio_signature(request: Request, form_params: dict[str, str]) -> None:
    """Validate Twilio signature. BASE_URL must match the URL set in Twilio Console."""
    token = _settings.twilio_auth_token
    if not token or token in ("your_twilio_auth_token", ""):
        return
    if _settings.environment == "development":
        return
    try:
        from twilio.request_validator import RequestValidator
    except ImportError:
        return

    signature = request.headers.get("X-Twilio-Signature", "")
    url = _twilio_validation_url(request)
    validator = RequestValidator(token)
    is_valid = validator.validate(url, form_params, signature)
    if not is_valid:
        print(f"[WhatsApp] Invalid Twilio signature for URL {url}")
        raise HTTPException(status_code=403, detail="Invalid Twilio signature")


@router.post("/webhook/whatsapp")
async def whatsapp_webhook(
    background_tasks: BackgroundTasks,
    request: Request,
):
    # Twilio signs every POST field — pass the full form body, not a hand-picked subset.
    raw_form = await request.form()
    form_params = {k: str(v) for k, v in raw_form.items()}

    From = form_params.get("From", "")
    Body = form_params.get("Body", "")
    ButtonText = form_params.get("ButtonText")
    ButtonPayload = form_params.get("ButtonPayload")
    ListId = form_params.get("ListId")
    ListTitle = form_params.get("ListTitle")
    InteractiveData = form_params.get("InteractiveData")
    try:
        NumMedia = int(form_params.get("NumMedia") or 0)
    except ValueError:
        NumMedia = 0
    MediaUrl0 = form_params.get("MediaUrl0")
    MediaContentType0 = form_params.get("MediaContentType0")

    if not From:
        raise HTTPException(status_code=400, detail="Missing From")

    _validate_twilio_signature(request, form_params)

    phone_number = From
    resolved_list_id = parse_list_selection_id(
        list_id=ListId or "",
        button_payload=ButtonPayload or "",
        interactive_data=InteractiveData or "",
    )
    user_message = build_inbound_user_message(
        body=Body or "",
        button_text=ButtonText or "",
        list_title=ListTitle or "",
        list_id=ListId or resolved_list_id,
        button_payload=ButtonPayload or "",
        interactive_data=InteractiveData or "",
    )
    session_id = f"wa_{phone_number}"

    client_ip = request.client.host if request.client else "unknown"
    print(f"[WhatsApp] INBOUND ip={client_ip} from={From} body={user_message!r}")

    # RESTART45 — reply in TwiML immediately (does not depend on outbound Twilio API / tunnel follow-up)
    if _is_restart_command(user_message):
        reset_msg = await _handle_restart45(session_id, phone_number)
        print(f"[WhatsApp] RESTART45 reset OK for {From}")
        return Response(content=twiml_response(reset_msg), media_type="application/xml")

    background_tasks.add_task(
        handle_whatsapp_message_bg,
        session_id,
        phone_number,
        user_message,
        NumMedia,
        MediaUrl0,
        MediaContentType0 or "",
        ButtonText or "",
        ButtonPayload or "",
        resolved_list_id,
    )

    return Response(
        content='<?xml version="1.0" encoding="UTF-8"?><Response></Response>',
        media_type="application/xml",
    )


async def handle_whatsapp_message_bg(
    session_id: str,
    phone_number: str,
    user_message: str,
    num_media: int = 0,
    media_url: Optional[str] = None,
    media_content_type: str = "",
    button_text: str = "",
    button_payload: str = "",
    list_id: str = "",
):
    try:
        await _handle_whatsapp_message_impl(
            session_id, phone_number, user_message, num_media, media_url,
            media_content_type, button_text, button_payload, list_id,
        )
    except Exception as e:
        import traceback
        print(f"[WhatsApp] Background handler error: {e}")
        traceback.print_exc()
        await log_event("API_ERROR", session_id=session_id,
                        data={"error": str(e), "phase": "whatsapp_handler_bg"})


async def _handle_whatsapp_message_impl(
    session_id: str,
    phone_number: str,
    user_message: str,
    num_media: int = 0,
    media_url: Optional[str] = None,
    media_content_type: str = "",
    button_text: str = "",
    button_payload: str = "",
    list_id: str = "",
):
    session = await get_session(session_id)

    # In-progress chat idle > N minutes — reset and send EVA intro; discard stale reply.
    if session and (user_message or num_media > 0) and is_session_idle_expired(session):
        stale_session = session
        print(f"[WhatsApp] Idle timeout reset for {phone_number} (>{_settings.session_idle_timeout_minutes}m)")
        await start_fresh_session(session_id, phone_number, reason="idle_timeout")
        session = await get_session(session_id)
        reply = build_idle_fresh_start_reply(stale_session, user_message)
        se.start_client_stage(session)
        session.add_message(MessageRole.ASSISTANT, reply)
        await save_session(session)
        await supabase_store.upsert_session_log(session)
        await send_whatsapp_message(to=phone_number, body=reply)
        return

    # After submit: only greetings / explicit new-enquiry phrases restart EVA flow.
    # Polite replies (Thank you, OK, etc.) keep the submitted session.
    if (
        session
        and _session_is_submitted(session)
        and (user_message or num_media > 0)
        and _is_new_enquiry_intent(user_message)
        and not _is_post_submit_polite_reply(user_message)
    ):
        print(f"[WhatsApp] New enquiry restart for {phone_number} msg={user_message!r}")
        await start_fresh_session(session_id, phone_number, reason="new_enquiry_after_submit")
        session = await get_session(session_id)

    # Greeting mid-flow (Hi bro, Namaste, etc.) — restart with full EVA welcome + qualification flow.
    if (
        session
        and user_message
        and not _session_is_submitted(session)
        and not session.flow_state.get("project_declined")
        and is_greeting_message(user_message)
        and had_conversation_progress(session)
    ):
        print(f"[WhatsApp] Greeting restart for {phone_number} msg={user_message!r}")
        await start_fresh_session(session_id, phone_number, reason="greeting_restart")
        session = await get_session(session_id)

    if session is None:
        session = Session(
            session_id=session_id,
            phone_number=phone_number,
            channel="whatsapp",
            conversation_stage=ConversationStage.ROUTING,
            created_at=datetime.utcnow(),
            last_active=datetime.utcnow(),
        )
        await log_event("SESSION_START", session_id=session_id,
                        data={"phone": phone_number, "channel": "whatsapp"})
        await save_session(session)
        if not user_message and num_media == 0:
            se.start_client_stage(session)
            vendor_msg = await register_tatva_user_for_session(session)
            body = vendor_msg or hybrid_flow.first_client_message()
            session.add_message(MessageRole.ASSISTANT, body)
            await save_session(session)
            await send_whatsapp_message(to=phone_number, body=body)
            return

    # Media upload handling (stage 9 — attachments, or edit-details file update)
    if num_media > 0 and media_url:
        meta = await save_attachment(session, media_url, media_content_type)
        if meta:
            hybrid_flow.init_flow(session)
            file_ack = "Thank you! We received your file."
            if edit_flow.awaiting_file_upload(session):
                reply, outbound_step, _handled = edit_flow.complete_file_upload(session)
                await save_session(session)
                await supabase_store.upsert_session_log(session)
                combined = f"{file_ack}\n\n{reply}".strip()
                await send_context_then_mcq_list(phone_number, combined, outbound_step)
                return
            if hybrid_flow.pending_file_upload(session):
                follow_up = hybrid_flow.complete_attachment_upload(session)
                await save_session(session)
                await supabase_store.upsert_session_log(session)
                combined = f"{file_ack}\n\n{follow_up}".strip()
                outbound_step = (
                    get_final_review_outbound_step(session)
                    if se.fs_current_stage(session) == "final_review"
                    else None
                )
                await send_context_then_mcq_list(phone_number, combined, outbound_step)
                return
            session.mark_field_complete("has_attachments", True)
            await save_session(session)
            await send_whatsapp_message(
                to=phone_number,
                body=f"{file_ack} Our team will review it with your enquiry.",
            )
            return

    if not user_message:
        return

    if se.fs_current_stage(session) == "service_selection":
        print(
            f"[WhatsApp] service_selection inbound "
            f"list_id={list_id!r} body={user_message!r} payload={button_payload!r}"
        )

    controller = get_controller()
    try:
        agent_response = await controller.process_message(
            session=session,
            user_message=user_message,
            channel="whatsapp",
            button_text=button_text or None,
            button_payload=button_payload or None,
            list_id=list_id or None,
        )
    except Exception as e:
        print(f"[WhatsApp] Error: {e}")
        await log_event("API_ERROR", session_id=session_id,
                        data={"error": str(e), "phase": "whatsapp_handler"})
        fallback = "Could you give me just a moment? I'm pulling your details together."
        await save_session(session)
        await send_whatsapp_message(to=phone_number, body=fallback)
        return

    await save_session(agent_response.session)
    await supabase_store.upsert_session_log(agent_response.session)

    if agent_response.summary_generated and agent_response.session.summary:
        await supabase_store.persist_terminal_enquiry(agent_response.session)
        try:
            from backend.schemas.summary import ProjectSummary
            summary_obj = ProjectSummary.model_validate(agent_response.session.summary)
            await supabase_store.save_summary(summary_obj, phone_number=phone_number)
        except Exception as e:
            print(f"[WhatsApp] summary save error: {e}")

        confirmation = (agent_response.text or "").strip()
        if confirmation:
            await send_whatsapp_message(to=phone_number, body=confirmation)
        follow_up = (agent_response.follow_up_text or "").strip()
        if follow_up:
            await send_whatsapp_message(to=phone_number, body=follow_up)
        await log_event(
            "CONVERSATION_ENDED",
            session_id=session_id,
            data={"reason": "enquiry_submitted", "channel": "whatsapp"},
        )
        return

    # Already submitted — send text only (no review list / MCQ follow-ups).
    session_out = agent_response.session
    if _session_is_submitted(session_out):
        reply = (agent_response.text or "").strip()
        if reply:
            await send_whatsapp_message(to=phone_number, body=reply)
        return

    if session_out.flow_state.get("project_declined"):
        await supabase_store.persist_terminal_enquiry(session_out)
        reply = (agent_response.text or "").strip()
        if reply:
            await send_whatsapp_message(to=phone_number, body=reply)
        await log_event(
            "CONVERSATION_ENDED",
            session_id=session_id,
            data={"reason": "project_declined", "channel": "whatsapp"},
        )
        return

    if session_out.flow_state.get("vendor_blocked"):
        reply = (agent_response.text or VENDOR_BLOCKED_MESSAGE).strip()
        if reply:
            await send_whatsapp_message(to=phone_number, body=reply)
        await log_event(
            "CONVERSATION_ENDED",
            session_id=session_id,
            data={"reason": "vendor_blocked", "channel": "whatsapp"},
        )
        return

    reply = (agent_response.text or "").strip()
    if not reply:
        print(f"[WhatsApp] Empty reply for message={user_message!r}")
        reply = "Thanks — could you repeat that? Please continue with the current step."

    if edit_flow.is_active(session_out):
        outbound_step = edit_flow.get_outbound_step(session_out)
    elif se.fs_current_stage(session_out) == "final_review":
        outbound_step = get_final_review_outbound_step(session_out)
    else:
        outbound_step = hybrid_flow.get_current_step(session_out)
        if (
            outbound_step is None
            and not session_out.service_category
            and se.fs_current_stage(session_out) == "service_selection"
        ):
            outbound_step = get_service_selection_outbound_step(session_out)
            uses_list = outbound_step.get("twilio_content_sid") or outbound_step.get("use_dynamic_list")
            if not uses_list:
                menu_body = hybrid_flow.format_mcq_message(outbound_step)
                if menu_body not in reply:
                    reply = f"{reply}\n\n{menu_body}".strip() if reply else menu_body
    outbound_step = enrich_whatsapp_mcq_step(outbound_step)
    uses_interactive_list = (
        outbound_step
        and outbound_step.get("type") == "mcq"
        and (
            outbound_step.get("twilio_content_sid")
            or outbound_step.get("use_dynamic_list")
        )
    )
    if (
        outbound_step
        and outbound_step.get("type") == "mcq"
        and not uses_interactive_list
    ):
        menu_body = hybrid_flow.format_mcq_message(outbound_step)
        if menu_body not in reply:
            reply = f"{reply}\n\n{menu_body}".strip() if reply else menu_body
    is_final_review_list = (
        outbound_step
        and outbound_step.get("field") in ("__final_review__", "__edit_post__")
    )
    if is_final_review_list:
        await send_context_then_mcq_list(phone_number, reply, outbound_step)
        return

    if uses_interactive_list:
        prompt_text = str(outbound_step.get("prompt", "")).strip()
        list_prompt = str(outbound_step.get("twilio_list_prompt", "")).strip()
        is_service_selection_list = (
            outbound_step.get("field") == "service_category"
            or outbound_step.get("stage") == "service_selection"
        )
        if is_service_selection_list:
            transition = (reply or "").strip()
            for chunk in (prompt_text, list_prompt):
                if chunk:
                    transition = transition.replace(chunk, "").strip()
            if not transition:
                transition = hybrid_flow.SERVICE_SELECTION_TRANSITION
            await send_whatsapp_message(to=phone_number, body=transition)
            await asyncio.sleep(1.0)
            await send_whatsapp_flow(
                to=phone_number,
                body=list_prompt or prompt_text or "Choose your service",
                step=outbound_step,
            )
            return
        # Other interactive lists: transition text first, then the list-picker body.
        if reply:
            cleaned = reply
            for chunk in (prompt_text, list_prompt):
                if chunk:
                    cleaned = cleaned.replace(chunk, "").strip()
            if cleaned:
                await send_whatsapp_message(to=phone_number, body=cleaned)
        reply = list_prompt or prompt_text or "Please choose one option."
    await send_whatsapp_flow(
        to=phone_number,
        body=reply,
        step=outbound_step,
    )


@router.get("/webhook/whatsapp/health")
async def whatsapp_webhook_health():
    """Quick check that BASE_URL/tunnel points at this server."""
    return {
        "ok": True,
        "environment": _settings.environment,
        "base_url": _settings.base_url,
        "restart_command": "RESTART45 or any message after enquiry submit",
    }

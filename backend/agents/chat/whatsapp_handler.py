"""
TatvaOps – WhatsApp Webhook Handler (Twilio)
EVA routing + specialized consultants + media uploads.
"""
from __future__ import annotations
import asyncio
from datetime import datetime, timedelta
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
from backend.integrations.tatva_users import register_phone_user
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
MEDIA_UPLOAD_DEBOUNCE_SEC = 2.5
FILE_UPLOAD_STRAGGLER_WINDOW_SEC = 8.0
_media_session_locks: dict[str, asyncio.Lock] = {}
MORE_FILE_UPLOAD_FIELD = "__more_file_upload__"
RETURNING_EDIT_DECISION_FIELD = "__returning_edit_info__"
RETURNING_PROFILE_FIELD = "__returning_profile_field__"


def _media_session_lock(session_id: str) -> asyncio.Lock:
    lock = _media_session_locks.get(session_id)
    if lock is None:
        lock = asyncio.Lock()
        _media_session_locks[session_id] = lock
    return lock


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


def _collect_twilio_media_items(form_params: dict[str, str]) -> list[tuple[str, str]]:
    try:
        num_media = int(form_params.get("NumMedia") or 0)
    except ValueError:
        num_media = 0
    items: list[tuple[str, str]] = []
    for i in range(num_media):
        url = (form_params.get(f"MediaUrl{i}") or "").strip()
        if url:
            items.append((url, form_params.get(f"MediaContentType{i}") or ""))
    return items


def _file_upload_recently_completed(session: Session) -> bool:
    completed_at = session.flow_state.get("file_upload_completed_at")
    if not completed_at:
        return False
    try:
        finished = datetime.fromisoformat(str(completed_at))
    except ValueError:
        return False
    return datetime.utcnow() - finished < timedelta(seconds=FILE_UPLOAD_STRAGGLER_WINDOW_SEC)


def _more_file_upload_step() -> dict:
    return {
        "id": "upload_more_files",
        "type": "mcq",
        "field": MORE_FILE_UPLOAD_FIELD,
        "prompt": "Do you want to add or upload multiple files?",
        "twilio_list_prompt": "Do you want to upload more files?",
        "options": [
            {"label": "Yes", "value": "yes"},
            {"label": "No", "value": "no"},
        ],
    }


def _parse_yes_no_choice(
    user_message: str,
    *,
    list_id: str = "",
    button_payload: str = "",
    button_text: str = "",
) -> Optional[bool]:
    for raw in (list_id, button_payload, button_text, user_message):
        value = (raw or "").strip().lower()
        if value in {"yes", "y"}:
            return True
        if value in {"no", "n", "skip", "later"}:
            return False
    return None


def _first_name(name: str) -> str:
    parts = [p for p in (name or "").strip().split() if p]
    return parts[0] if parts else ""


def _touch_session_activity(session: Session) -> None:
    session.last_active = datetime.utcnow()


def _returning_profile_selection(
    *,
    list_id: str = "",
    button_payload: str = "",
    button_text: str = "",
    user_message: str = "",
) -> str:
    """Normalize list tap or typed reply for returning-user profile edit menu."""
    for raw in (list_id, button_payload, button_text, user_message):
        selected = (raw or "").strip().lower()
        if not selected:
            continue
        if selected in {"client_name", "name"}:
            return "client_name"
        if selected == "email":
            return "email"
        if selected in {"continue", "no", "n", "skip", "done"}:
            return "continue"
    return ""


async def _send_returning_mcq_prompt(
    phone_number: str,
    context_body: str,
    step: dict,
) -> None:
    await send_context_then_mcq_list(
        phone_number,
        context_body,
        enrich_whatsapp_mcq_step(step),
    )


def _returning_edit_decision_step() -> dict:
    return {
        "id": "returning_edit_decision",
        "type": "mcq",
        "field": RETURNING_EDIT_DECISION_FIELD,
        "prompt": "Do you want to Edit Your Info?",
        "twilio_list_prompt": "Do you want to Edit Your Info?",
        "options": [
            {"label": "Yes", "value": "yes"},
            {"label": "No", "value": "no"},
        ],
    }


def _returning_profile_field_step() -> dict:
    return {
        "id": "returning_profile_field",
        "type": "mcq",
        "field": RETURNING_PROFILE_FIELD,
        "prompt": "What would you like to edit?",
        "twilio_list_prompt": "What would you like to edit?",
        "options": [
            {"label": "Name", "value": "client_name"},
            {"label": "Email", "value": "email"},
            {"label": "Continue", "value": "continue"},
        ],
    }


def _is_registered_returning_user(session: Session) -> bool:
    return bool(
        session.extracted_fields.get("tatva_user_id")
        or session.flow_state.get("tatva_user_registered")
    )


def _is_in_returning_user_prompt(session: Session) -> bool:
    """True while the user is mid returning-user re-entry (edit decision / profile)."""
    return bool(
        session.flow_state.get("awaiting_returning_edit_decision")
        or session.flow_state.get("awaiting_returning_profile_field")
        or session.flow_state.get("awaiting_returning_profile_value")
    )


async def _hydrate_returning_profile_from_tatva(session: Session) -> None:
    if session.extracted_fields.get("client_name") and session.extracted_fields.get("email"):
        return
    payload = await register_phone_user(session.phone_number or "", session_id=session.session_id)
    if not payload:
        return
    data = payload.get("data") or {}
    user = data.get("user") or {}
    user_id = user.get("_id")
    if user_id and not session.extracted_fields.get("tatva_user_id"):
        session.extracted_fields["tatva_user_id"] = str(user_id)
        if "tatva_user_id" not in session.completed_fields:
            session.completed_fields.append("tatva_user_id")
    name = (
        user.get("name")
        or user.get("fullName")
        or user.get("firstName")
        or user.get("displayName")
        or ""
    )
    email = user.get("email") or ""
    if name and not session.extracted_fields.get("client_name"):
        se.mark_field_validated(session, "client_name", str(name).strip())
    if email and not session.extracted_fields.get("email"):
        if se.is_valid_gmail_address(str(email).strip()):
            se.mark_field_validated(session, "email", str(email).strip())


def _returning_user_greeting_text(session: Session) -> str:
    raw_name = str(session.extracted_fields.get("client_name") or "").strip()
    email = str(session.extracted_fields.get("email") or "").strip()
    first = _first_name(raw_name)
    greet_name = first or "there"
    if email:
        return (
            f"Welcome back, {greet_name}! 👋\n\n"
            f"We found your TatvaOps profile.\n"
            f"Email: {email}"
        )
    return (
        f"Welcome back, {greet_name}! 👋\n\n"
        "We found your TatvaOps profile."
    )


def _prepare_returning_user_client_stage(session: Session) -> None:
    phone = (session.extracted_fields.get("phone_number") or session.phone_number or "").strip()
    if phone.lower().startswith("whatsapp:"):
        phone = phone.split(":", 1)[-1]
    preserved = {
        "tatva_user_id": str(session.extracted_fields.get("tatva_user_id") or "").strip(),
        "client_name": str(session.extracted_fields.get("client_name") or "").strip(),
        "email": str(session.extracted_fields.get("email") or "").strip(),
        "city": str(session.extracted_fields.get("city") or "").strip(),
        "property_location": str(session.extracted_fields.get("property_location") or "").strip(),
        "preferred_contact_time": str(session.extracted_fields.get("preferred_contact_time") or "").strip(),
        "phone_number": phone,
    }
    se.clear_prior_enquiry_qualification(session)
    session.conversation_stage = ConversationStage.ROUTING
    session.flow_state = {}
    edit_flow.clear_edit_mode(session)
    hybrid_flow.init_flow(session)
    se.start_client_stage(session)
    if preserved["phone_number"]:
        se.mark_field_validated(session, "phone_number", preserved["phone_number"])
    if preserved["client_name"]:
        se.mark_field_validated(session, "client_name", preserved["client_name"])
    if preserved["email"] and se.is_valid_gmail_address(preserved["email"]):
        se.mark_field_validated(session, "email", preserved["email"])
    se.mark_field_validated(session, "city", preserved["city"] or "As per TatvaOps profile")
    se.mark_field_validated(
        session, "property_location", preserved["property_location"] or "As per TatvaOps profile"
    )
    se.mark_field_validated(
        session,
        "preferred_contact_time",
        preserved["preferred_contact_time"] or "as_per_profile",
    )
    if preserved["tatva_user_id"]:
        session.extracted_fields["tatva_user_id"] = preserved["tatva_user_id"]
        if "tatva_user_id" not in session.completed_fields:
            session.completed_fields.append("tatva_user_id")
    session.flow_state["returning_user_reentry"] = True
    session.flow_state.pop("current_step_id", None)
    se.reconcile_session(session)
    _touch_session_activity(session)


async def _send_returning_user_reentry_prompt(session: Session, phone_number: str) -> None:
    _touch_session_activity(session)
    session.flow_state["awaiting_returning_edit_decision"] = True
    await save_session(session)
    await supabase_store.upsert_session_log(session)
    await send_context_then_mcq_list(
        phone_number,
        _returning_user_greeting_text(session),
        _returning_edit_decision_step(),
    )


async def _send_willing_to_create_project_prompt(session: Session, phone_number: str) -> None:
    _prepare_returning_user_client_stage(session)
    _touch_session_activity(session)
    step = hybrid_flow.get_current_step(session)
    if step:
        await _send_returning_mcq_prompt(phone_number, "", step)
    else:
        await send_whatsapp_message(
            to=phone_number,
            body="Would you like to proceed with creating your project?",
        )


def _in_file_upload_flow(session: Session) -> bool:
    return bool(
        edit_flow.awaiting_file_upload(session)
        or hybrid_flow.pending_file_upload(session)
        or session.flow_state.get("awaiting_more_upload_decision")
        or session.flow_state.get("awaiting_additional_file_upload")
    )


def _cancel_pending_upload_follow_up(session: Session) -> None:
    """Invalidate any in-flight debounced upload follow-up tasks."""
    session.flow_state["media_upload_batch_version"] = (
        int(session.flow_state.get("media_upload_batch_version") or 0) + 1
    )


def _looks_like_upload_filename(message: str) -> bool:
    lower = (message or "").strip().lower()
    if not lower:
        return False
    return lower.endswith((
        ".png", ".jpg", ".jpeg", ".gif", ".webp", ".pdf", ".dwg", ".doc", ".docx",
    ))


async def _send_file_upload_follow_up(
    session: Session,
    phone_number: str,
    *,
    file_ack: str | None = None,
    ask_for_more: bool = True,
) -> None:
    if ask_for_more:
        hybrid_flow.sync_attachment_fields(session, complete_step=False)
    if file_ack is None:
        file_ack = hybrid_flow.file_upload_ack_message(session)
    if ask_for_more:
        session.flow_state["awaiting_more_upload_decision"] = True
        await send_context_then_mcq_list(phone_number, file_ack, _more_file_upload_step())
        return

    if edit_flow.awaiting_file_upload(session):
        reply, outbound_step, _handled = edit_flow.complete_file_upload(session)
        combined = f"{file_ack}\n\n{reply}".strip()
        await send_context_then_mcq_list(phone_number, combined, outbound_step)
        return

    follow_up = hybrid_flow.complete_attachment_upload(session)
    outbound_step = (
        get_final_review_outbound_step(session)
        if se.fs_current_stage(session) == "final_review"
        else hybrid_flow.get_current_step(session)
    )
    if outbound_step and outbound_step.get("type") == "file_request":
        hybrid_flow._force_advance_past_file_upload(session)
        follow_up = hybrid_flow._next_step_message(session) or ""
        follow_up = hybrid_flow.strip_post_upload_follow_up(session, follow_up)
        outbound_step = (
            get_final_review_outbound_step(session)
            if se.fs_current_stage(session) == "final_review"
            else hybrid_flow.get_current_step(session)
        )

    follow_up = hybrid_flow.strip_post_upload_follow_up(session, follow_up or "")
    if outbound_step and outbound_step.get("type") == "mcq":
        prompt_text = str(outbound_step.get("prompt", "")).strip()
        list_prompt = str(outbound_step.get("twilio_list_prompt", "")).strip()
        cleaned_follow_up = follow_up
        for chunk in (prompt_text, list_prompt):
            if chunk:
                idx = cleaned_follow_up.find(chunk)
                if idx != -1:
                    cleaned_follow_up = cleaned_follow_up[:idx].strip()
        follow_up = cleaned_follow_up
        context_body = (file_ack or "").strip()
    else:
        context_body = f"{file_ack}\n\n{follow_up}".strip() if follow_up else (file_ack or "").strip()

    await send_context_then_mcq_list(phone_number, context_body, outbound_step)


async def _debounced_file_upload_follow_up(
    session_id: str,
    phone_number: str,
    batch_version: int,
) -> None:
    await asyncio.sleep(MEDIA_UPLOAD_DEBOUNCE_SEC)
    async with _media_session_lock(session_id):
        session = await get_session(session_id)
        if not session:
            return
        if session.flow_state.get("media_upload_batch_version") != batch_version:
            return
        if session.flow_state.get("media_upload_follow_up_sent") == batch_version:
            return

        hybrid_flow.init_flow(session)
        awaiting_additional = session.flow_state.get("awaiting_additional_file_upload")
        awaiting_more = session.flow_state.get("awaiting_more_upload_decision")
        if (
            not edit_flow.awaiting_file_upload(session)
            and not hybrid_flow.pending_file_upload(session)
            and not awaiting_additional
            and not awaiting_more
        ):
            return

        session.flow_state["media_upload_follow_up_sent"] = batch_version
        session.flow_state["file_upload_completed_at"] = datetime.utcnow().isoformat()
        if awaiting_additional:
            session.flow_state.pop("awaiting_additional_file_upload", None)
        await save_session(session)
        await supabase_store.upsert_session_log(session)
        await _send_file_upload_follow_up(
            session,
            phone_number,
            ask_for_more=not awaiting_additional,
        )
        await save_session(session)
        await supabase_store.upsert_session_log(session)


async def _schedule_file_upload_follow_up(session: Session, phone_number: str) -> None:
    batch_version = int(session.flow_state.get("media_upload_batch_version") or 0) + 1
    session.flow_state["media_upload_batch_version"] = batch_version
    session.flow_state.pop("media_upload_follow_up_sent", None)
    await save_session(session)
    asyncio.create_task(_debounced_file_upload_follow_up(session.session_id, phone_number, batch_version))


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
    media_items = _collect_twilio_media_items(form_params)
    MediaUrl0 = media_items[0][0] if media_items else form_params.get("MediaUrl0")
    MediaContentType0 = media_items[0][1] if media_items else (form_params.get("MediaContentType0") or "")

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
        media_items,
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
    media_items: list[tuple[str, str]] | None = None,
    button_text: str = "",
    button_payload: str = "",
    list_id: str = "",
):
    try:
        await _handle_whatsapp_message_impl(
            session_id, phone_number, user_message, num_media, media_items or [],
            button_text, button_payload, list_id,
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
    media_items: list[tuple[str, str]] | None = None,
    button_text: str = "",
    button_payload: str = "",
    list_id: str = "",
):
    media_items = media_items or []
    session = await get_session(session_id)

    if session and (user_message or num_media > 0):
        _touch_session_activity(session)

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
        and not _is_in_returning_user_prompt(session)
    ):
        print(f"[WhatsApp] New enquiry restart for {phone_number} msg={user_message!r}")
        await _hydrate_returning_profile_from_tatva(session)
        if _is_registered_returning_user(session):
            await _send_returning_user_reentry_prompt(session, phone_number)
            await save_session(session)
            await supabase_store.upsert_session_log(session)
            return
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
    if num_media > 0 and media_items:
        async with _media_session_lock(session_id):
            session = await get_session(session_id) or session
            hybrid_flow.init_flow(session)
            saved_any = False
            for media_url, media_content_type in media_items:
                meta = await save_attachment(session, media_url, media_content_type)
                if meta:
                    saved_any = True
            if saved_any:
                if session.flow_state.get("awaiting_more_upload_decision"):
                    session.flow_state.pop("awaiting_more_upload_decision", None)
                    session.flow_state["awaiting_additional_file_upload"] = True
                if _in_file_upload_flow(session):
                    await _schedule_file_upload_follow_up(session, phone_number)
                    await save_session(session)
                    await supabase_store.upsert_session_log(session)
                    return
                if _file_upload_recently_completed(session):
                    hybrid_flow.refresh_attachment_field_count(session)
                    await save_session(session)
                    await supabase_store.upsert_session_log(session)
                    return
                session.mark_field_complete("has_attachments", True)
                hybrid_flow.sync_attachment_fields(session)
                await save_session(session)
                await supabase_store.upsert_session_log(session)
                ack = (
                    f"{hybrid_flow.file_upload_ack_message(session)} "
                    f"Our team will review {'them' if hybrid_flow.attachment_count(session) > 1 else 'it'} with your enquiry."
                )
                await send_whatsapp_message(to=phone_number, body=ack)
                return

    if not user_message:
        return

    if session.flow_state.get("awaiting_returning_edit_decision"):
        wants_edit = _parse_yes_no_choice(
            user_message,
            list_id=list_id,
            button_payload=button_payload,
            button_text=button_text,
        )
        if wants_edit is None:
            await send_context_then_mcq_list(
                phone_number,
                "Please choose *Yes* or *No*.",
                _returning_edit_decision_step(),
            )
            return
        session.flow_state.pop("awaiting_returning_edit_decision", None)
        if wants_edit:
            session.flow_state["awaiting_returning_profile_field"] = True
            await save_session(session)
            await supabase_store.upsert_session_log(session)
            await _send_returning_mcq_prompt(phone_number, "", _returning_profile_field_step())
            return
        await _send_willing_to_create_project_prompt(session, phone_number)
        await save_session(session)
        await supabase_store.upsert_session_log(session)
        return

    if session.flow_state.get("awaiting_returning_profile_field"):
        chosen = _returning_profile_selection(
            list_id=list_id,
            button_payload=button_payload,
            button_text=button_text,
            user_message=user_message,
        )
        if chosen == "continue":
            session.flow_state.pop("awaiting_returning_profile_field", None)
            await _send_willing_to_create_project_prompt(session, phone_number)
            await save_session(session)
            await supabase_store.upsert_session_log(session)
            return
        if chosen in {"client_name", "email"}:
            session.flow_state.pop("awaiting_returning_profile_field", None)
            session.flow_state["awaiting_returning_profile_value"] = True
            session.flow_state["returning_profile_edit_field"] = chosen
            prompt = (
                "Please type your name."
                if chosen == "client_name"
                else "Please type your Gmail address (or reply skip)."
            )
            await save_session(session)
            await supabase_store.upsert_session_log(session)
            await send_whatsapp_message(to=phone_number, body=prompt)
            return
        await _send_returning_mcq_prompt(
            phone_number,
            "Please choose *Name*, *Email*, or *Continue*.",
            _returning_profile_field_step(),
        )
        return

    if session.flow_state.get("awaiting_returning_profile_value"):
        field = str(session.flow_state.get("returning_profile_edit_field") or "")
        text = (user_message or "").strip()
        if field == "email":
            if text.lower() in {"skip", "none"}:
                se.mark_field_validated(session, "email", "")
            elif not se.is_valid_gmail_address(text):
                await send_whatsapp_message(
                    to=phone_number,
                    body="Please enter a valid Gmail address, or reply skip.",
                )
                return
            else:
                se.mark_field_validated(session, "email", text)
        elif field == "client_name":
            if not text:
                await send_whatsapp_message(to=phone_number, body="Please type your name.")
                return
            se.mark_field_validated(session, "client_name", text)
        session.flow_state.pop("awaiting_returning_profile_value", None)
        session.flow_state.pop("returning_profile_edit_field", None)
        session.flow_state["awaiting_returning_profile_field"] = True
        await save_session(session)
        await supabase_store.upsert_session_log(session)
        await _send_returning_mcq_prompt(
            phone_number,
            "Updated successfully.",
            _returning_profile_field_step(),
        )
        return

    if session.flow_state.get("awaiting_more_upload_decision"):
        wants_more = _parse_yes_no_choice(
            user_message,
            list_id=list_id,
            button_payload=button_payload,
            button_text=button_text,
        )
        if wants_more is None:
            await send_context_then_mcq_list(
                phone_number,
                "Please choose *Yes* or *No*.",
                _more_file_upload_step(),
            )
            return
        if wants_more:
            session.flow_state.pop("awaiting_more_upload_decision", None)
            session.flow_state["awaiting_additional_file_upload"] = True
            await save_session(session)
            await supabase_store.upsert_session_log(session)
            await send_whatsapp_message(
                to=phone_number,
                body=hybrid_flow.additional_file_upload_prompt(),
            )
            return
        session.flow_state.pop("awaiting_more_upload_decision", None)
        _cancel_pending_upload_follow_up(session)
        await save_session(session)
        await supabase_store.upsert_session_log(session)
        await _send_file_upload_follow_up(
            session,
            phone_number,
            file_ack="",
            ask_for_more=False,
        )
        await save_session(session)
        await supabase_store.upsert_session_log(session)
        return

    if (
        _in_file_upload_flow(session)
        and _looks_like_upload_filename(user_message)
        and not _parse_yes_no_choice(
            user_message,
            list_id=list_id,
            button_payload=button_payload,
            button_text=button_text,
        )
    ):
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
        field_name = outbound_step.get("field")
        is_service_selection_list = (
            field_name == "service_category"
            or outbound_step.get("stage") == "service_selection"
        )
        if is_service_selection_list:
            transition = (reply or "").strip()
            for chunk in (prompt_text, list_prompt):
                if chunk:
                    idx = transition.find(chunk)
                    if idx != -1:
                        transition = transition[:idx].strip()
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
        # For all other interactive lists, avoid repeating the question/options as plain text.
        if reply:
            cleaned = reply
            for chunk in (prompt_text, list_prompt):
                if chunk:
                    idx = cleaned.find(chunk)
                    if idx != -1:
                        cleaned = cleaned[:idx].strip()
            if cleaned:
                await send_whatsapp_message(to=phone_number, body=cleaned)
                await asyncio.sleep(1.0)
        reply = list_prompt or prompt_text or "Tap *Choose option* below to select your answer."
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

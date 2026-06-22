"""
TatvaOps – WhatsApp Webhook Handler (Twilio)
EVA routing + specialized consultants + media uploads.
"""
from __future__ import annotations
import asyncio
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, HTTPException, Request, Response

from backend.config import get_settings
from backend.schemas.session import Session, ConversationStage, MessageRole
from backend.intelligence.conversation_controller import get_controller
from backend.intelligence import hybrid_flow
from backend.intelligence import edit_flow
from backend.intelligence import stage_engine as se
from backend.intelligence.nova_router import get_service_selection_outbound_step
from backend.intelligence.qualification_builder import get_final_review_outbound_step
from backend.integrations.tatva_users import (
    check_phone_user,
    check_tatva_phone_for_session,
    is_vendor_response,
    VENDOR_BLOCKED_MESSAGE,
)
from backend.integrations.returning_user_flow import (
    existing_user_welcome_text,
    parse_returning_location_choice,
    position_session_for_project_decision,
    apply_returning_location_choice,
    prepare_returning_user_for_project_decision,
    returning_edit_decision_step,
    returning_saved_location_context,
    returning_saved_location_step,
    WILLING_TO_CREATE_PROJECT_FALLBACK,
)
from backend.integrations.tatva_user_addresses import get_cached_user_addresses
from backend.storage.redis_store import get_session, save_session, claim_inbound_message
from backend.storage import supabase_store
from backend.storage.media_store import save_attachment
from backend.agents.chat.twilio_client import (
    enrich_whatsapp_mcq_step,
    mcq_uses_interactive_delivery,
    send_context_then_mcq_list,
    send_say_hi_prompt,
    send_whatsapp_message,
    send_whatsapp_flow,
    send_whatsapp_attachment_cta_links,
    twiml_response,
    _format_mcq_plain_fallback,
)
from backend.agents.chat.whatsapp_interactive import build_inbound_user_message, parse_list_selection_id
from backend.utils.logger import log_event
from backend.utils.session_idle import (
    is_session_idle_expired,
    is_greeting_message,
    had_conversation_progress,
    build_idle_fresh_start_reply,
    clear_cached_session,
    start_fresh_session,
)

router = APIRouter()
_settings = get_settings()
MEDIA_UPLOAD_DEBOUNCE_SEC = 2.5
FILE_UPLOAD_STRAGGLER_WINDOW_SEC = 8.0
_session_locks: dict[str, asyncio.Lock] = {}
MORE_FILE_UPLOAD_FIELD = "__more_file_upload__"
RETURNING_EDIT_DECISION_FIELD = "__returning_edit_info__"
RETURNING_LOCATION_FIELD = "__returning_location__"
RETURNING_PROFILE_FIELD = "__returning_profile_field__"
RETURNING_USER_PHASE = "returning_user_phase"
RETURNING_MCQ_SENT_FIELD = "returning_mcq_sent_field"
RETURNING_GREETING_DEDUP_SEC = 12


def _normalize_inbound_text(message: str) -> str:
    return (message or "").strip().upper().replace(" ", "")


def _recent_returning_greeting_duplicate(
    session: Session,
    *,
    norm_msg: str,
    dedup_key: str,
) -> bool:
    """Suppress a second full welcome+location burst for the same inbound greeting."""
    if dedup_key and session.flow_state.get("last_returning_greeting_dedup_key") == dedup_key:
        return True
    if session.flow_state.get("last_returning_greeting_msg") != norm_msg:
        return False
    sent_at = str(session.flow_state.get("returning_greeting_sent_at") or "").strip()
    if not sent_at:
        return False
    try:
        stamp = sent_at.replace("Z", "")
        elapsed = (datetime.utcnow() - datetime.fromisoformat(stamp)).total_seconds()
    except Exception:
        return False
    return elapsed < RETURNING_GREETING_DEDUP_SEC


def _returning_user_phase(session: Session) -> str:
    return str(session.flow_state.get(RETURNING_USER_PHASE) or "")


def _set_returning_user_phase(session: Session, phase: str) -> None:
    if phase:
        session.flow_state[RETURNING_USER_PHASE] = phase
    else:
        session.flow_state.pop(RETURNING_USER_PHASE, None)


def _clear_returning_user_prompt_state(session: Session) -> None:
    session.flow_state.pop("awaiting_returning_edit_decision", None)
    session.flow_state.pop("awaiting_returning_location_decision", None)
    session.flow_state.pop("awaiting_returning_profile_field", None)
    session.flow_state.pop("awaiting_returning_profile_value", None)
    session.flow_state.pop("returning_profile_edit_field", None)
    session.flow_state.pop("returning_user_reentry", None)
    session.flow_state.pop("pending_outbound_mcq", None)
    _set_returning_user_phase(session, "")


def _session_lock(session_id: str) -> asyncio.Lock:
    lock = _session_locks.get(session_id)
    if lock is None:
        lock = asyncio.Lock()
        _session_locks[session_id] = lock
    return lock


def _normalize_restart_command(message: str) -> str:
    return (message or "").strip().upper().replace(" ", "")


def _is_restart_command(message: str) -> bool:
    return _normalize_restart_command(message) == "RESTART45"


async def _handle_restart45(session_id: str, phone_number: str) -> str:
    """Clear session and return immediate TwiML (outbound Say Hi sent in background)."""
    await start_fresh_session(session_id, phone_number, reason="RESTART45")
    session = await get_session(session_id)
    if session:
        session.flow_state["awaiting_say_hi"] = True
        await save_session(session)
    step = hybrid_flow.say_hi_prompt_step()
    return "Session reset.\n\n" + _format_mcq_plain_fallback(
        hybrid_flow.say_hi_welcome_text(), step
    )


async def _send_say_hi_gate(session: Session, phone_number: str, *, remind: bool = False) -> None:
    """Show the Say Hi template until the user taps it."""
    body = hybrid_flow.say_hi_welcome_text(remind=remind)
    if not any(
        m.role == MessageRole.ASSISTANT and "tap on one of these options" in (m.content or "").lower()
        for m in session.conversation_history
    ):
        session.add_message(MessageRole.ASSISTANT, body)
    session.flow_state["awaiting_say_hi"] = True
    await save_session(session)
    await send_say_hi_prompt(phone_number, remind=remind)


async def _start_chat_after_say_hi(session: Session, phone_number: str) -> None:
    """Begin EVA flow after the user taps Say Hi."""
    session.flow_state.pop("awaiting_say_hi", None)
    se.start_client_stage(session)
    vendor_msg = await check_tatva_phone_for_session(session)
    if vendor_msg:
        body = vendor_msg
        session.add_message(MessageRole.ASSISTANT, body)
        await save_session(session)
        await send_whatsapp_message(to=phone_number, body=body)
        return
    if session.flow_state.get("tatva_phone_is_user"):
        session.flow_state["existing_user_flow_started"] = True
        session.flow_state["awaiting_returning_edit_decision"] = True
        body = existing_user_welcome_text(session)
        session.add_message(MessageRole.ASSISTANT, body)
        await save_session(session)
        await send_context_then_mcq_list(
            phone_number, body, returning_edit_decision_step()
        )
        return
    body = hybrid_flow.first_client_message()
    session.add_message(MessageRole.ASSISTANT, body)
    await save_session(session)
    await send_whatsapp_message(to=phone_number, body=body)


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


async def _send_returning_interactive_mcq_once(
    session: Session,
    phone_number: str,
    step: dict,
) -> None:
    """Send a single WhatsApp list-picker — never a separate plain-text copy of the question."""
    outbound = enrich_whatsapp_mcq_step(dict(step))
    field = str(outbound.get("field") or "")
    body = str(
        outbound.get("twilio_list_prompt")
        or outbound.get("prompt")
        or ""
    ).strip()
    session.flow_state[RETURNING_MCQ_SENT_FIELD] = field
    session.add_message(MessageRole.ASSISTANT, body)
    await save_session(session)
    await supabase_store.upsert_session_log(session)
    if mcq_uses_interactive_delivery(outbound):
        await send_whatsapp_flow(to=phone_number, body=body, step=outbound)
        return
    menu = hybrid_flow.format_mcq_message(outbound)
    await send_whatsapp_message(to=phone_number, body=menu)


def _clear_returning_mcq_sent_if_complete(session: Session) -> None:
    sent = session.flow_state.get(RETURNING_MCQ_SENT_FIELD)
    if sent and se.field_is_complete(session, str(sent)):
        session.flow_state.pop(RETURNING_MCQ_SENT_FIELD, None)


def _should_skip_duplicate_returning_outbound(session: Session, outbound_step: dict | None) -> bool:
    if not outbound_step:
        return False
    sent = str(session.flow_state.get(RETURNING_MCQ_SENT_FIELD) or "")
    field = str(outbound_step.get("field") or "")
    return bool(sent and field and sent == field)


def _strip_outbound_prompt_from_reply(reply: str, outbound_step: dict) -> str:
    cleaned = (reply or "").strip()
    for chunk in (
        str(outbound_step.get("prompt", "")).strip(),
        str(outbound_step.get("twilio_list_prompt", "")).strip(),
    ):
        if chunk:
            idx = cleaned.find(chunk)
            if idx != -1:
                cleaned = cleaned[:idx].strip()
    return cleaned


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
        if selected in {"property_location", "property location", "location", "property"}:
            return "property_location"
        if selected in {"continue", "no", "n", "skip", "done"}:
            return "continue"
    return ""


async def _send_returning_plain_mcq(
    phone_number: str,
    step: dict,
    *,
    context_body: str = "",
) -> None:
    """Single plain-text MCQ — avoids duplicate WhatsApp list-picker prompts."""
    plain_step = dict(step)
    plain_step["force_plain_mcq"] = True
    plain_step.pop("twilio_content_sid", None)
    plain_step.pop("use_dynamic_list", None)
    menu = hybrid_flow.format_step_message(plain_step, include_stage=False)
    body = "\n\n".join(part for part in ((context_body or "").strip(), menu) if part)
    await send_whatsapp_message(to=phone_number, body=body)


async def _send_returning_mcq_prompt(
    phone_number: str,
    context_body: str,
    step: dict,
) -> None:
    await _send_returning_plain_mcq(phone_number, step, context_body=context_body)


def _returning_edit_decision_step() -> dict:
    return returning_edit_decision_step()


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
            {"label": "Property location", "value": "property_location"},
            {"label": "Continue", "value": "continue"},
        ],
    }


def _prepare_returning_user_client_stage(session: Session) -> None:
    """Clear the prior enquiry and position a returning user at willing_to_create_project."""
    prepare_returning_user_for_project_decision(session)
    _touch_session_activity(session)


def _is_registered_returning_user(session: Session) -> bool:
    return bool(
        session.extracted_fields.get("tatva_user_id")
        or session.flow_state.get("tatva_user_registered")
        or session.flow_state.get("tatva_phone_is_user")
    )


def _is_in_returning_user_prompt(session: Session) -> bool:
    """True only while waiting for location confirmation or profile-edit replies."""
    if session.flow_state.get("awaiting_returning_location_decision"):
        return True
    return _returning_user_phase(session) in {
        "location_decision",
        "profile_field",
        "profile_value",
    }


async def _hydrate_returning_profile_from_tatva(session: Session, *, force: bool = False) -> None:
    from backend.integrations.tatva_users import hydrate_returning_user_profile

    await hydrate_returning_user_profile(session, force=force)


def _reset_stale_flow_for_returning_greeting(session: Session) -> None:
    """Drop stale qualification/review state before a returning-user welcome."""
    edit_flow.clear_edit_mode(session)
    session.flow_state.pop("returning_edit_flow_complete", None)
    for key in (
        "conversation_ended",
        "final_review_shown",
        "final_review_outbound_step",
        "current_step_id",
        "current_question",
        "pending_fields",
        "pending_outbound_mcq",
        "awaiting_returning_edit_decision",
        "awaiting_returning_location_decision",
        "awaiting_returning_profile_field",
        "awaiting_returning_profile_value",
        "returning_profile_edit_field",
        "returning_user_reentry",
        "existing_user_flow_started",
        "returning_reentry_in_progress",
        "returning_greeting_sent_at",
        "last_returning_greeting_msg",
        "last_returning_greeting_dedup_key",
        "project_declined",
    ):
        session.flow_state.pop(key, None)
    _set_returning_user_phase(session, "")


async def _ensure_registered_user_from_tatva(session: Session) -> bool:
    """Refresh Tatva check-phone and return True when this is a known user."""
    if session.flow_state.get("vendor_blocked"):
        return False

    payload = await check_phone_user(session.phone_number or "", session_id=session.session_id)
    if payload:
        if is_vendor_response(payload):
            session.flow_state["vendor_blocked"] = True
            session.flow_state["tatva_phone_checked"] = True
            return False
        data = payload.get("data") or {}
        is_user = bool(data.get("isUser"))
        session.flow_state["tatva_phone_checked"] = True
        session.flow_state["tatva_phone_is_user"] = is_user
        if is_user:
            session.flow_state["tatva_user_registered"] = True
            await _hydrate_returning_profile_from_tatva(session, force=True)
            return True
        session.flow_state["tatva_user_registered"] = False
        return False

    return _is_registered_returning_user(session)


async def _try_registered_user_greeting_restart(
    session: Session | None,
    session_id: str,
    phone_number: str,
    user_message: str,
    *,
    message_sid: str = "",
) -> bool:
    """
    Registered Tatva user said hi/hello — greet by name and offer edit Yes/No.
    Handles stale sessions stuck at final review or mid-flow.
    """
    if not is_greeting_message(user_message):
        return False

    stored = await get_session(session_id)
    if stored:
        session = stored

    norm_msg = _normalize_inbound_text(user_message)
    dedup_key = str(message_sid or "").strip() or f"{phone_number}:{norm_msg}"
    if session and _recent_returning_greeting_duplicate(
        session,
        norm_msg=norm_msg,
        dedup_key=dedup_key,
    ):
        print(f"[WhatsApp] Skip duplicate returning greeting for {phone_number}")
        return True

    if session is None:
        session = Session(
            session_id=session_id,
            phone_number=phone_number,
            channel="whatsapp",
            conversation_stage=ConversationStage.ROUTING,
            created_at=datetime.utcnow(),
            last_active=datetime.utcnow(),
        )
        await log_event(
            "SESSION_START",
            session_id=session_id,
            data={"phone": phone_number, "channel": "whatsapp", "reason": "returning_greeting"},
        )

    if not await _ensure_registered_user_from_tatva(session):
        if session and not session.conversation_history:
            await save_session(session)
        return False

    print(f"[WhatsApp] Returning-user greeting restart for {phone_number} msg={user_message!r}")
    _reset_stale_flow_for_returning_greeting(session)
    session.flow_state["returning_greeting_sent_at"] = datetime.utcnow().isoformat() + "Z"
    session.flow_state["last_returning_greeting_msg"] = norm_msg
    session.flow_state["last_returning_greeting_dedup_key"] = dedup_key
    session.add_message(MessageRole.USER, user_message)
    await save_session(session)
    await _send_returning_user_reentry_prompt(session, phone_number)
    return True


def _returning_user_greeting_text(session: Session) -> str:
    return existing_user_welcome_text(session)


async def _send_returning_location_prompt(session: Session, phone_number: str) -> None:
    from backend.integrations.tatva_user_addresses import load_user_addresses_for_session

    await load_user_addresses_for_session(session, force=True)
    session.flow_state["awaiting_returning_location_decision"] = True
    _set_returning_user_phase(session, "location_decision")
    step = returning_saved_location_step(session)
    outbound = enrich_whatsapp_mcq_step(dict(step))
    context_body = str(step.get("prompt") or returning_saved_location_context(session)).strip()
    field = str(outbound.get("field") or RETURNING_LOCATION_FIELD)
    list_prompt = str(
        outbound.get("twilio_list_prompt") or "Choose your saved location"
    ).strip()
    session.flow_state[RETURNING_MCQ_SENT_FIELD] = field
    session.add_message(MessageRole.ASSISTANT, f"{context_body}\n\n{list_prompt}".strip())
    await save_session(session)
    await supabase_store.upsert_session_log(session)
    if mcq_uses_interactive_delivery(outbound):
        await send_context_then_mcq_list(phone_number, context_body, outbound)
        return
    menu = _format_mcq_plain_fallback(list_prompt, outbound)
    if context_body.strip() != list_prompt.strip():
        body = f"{context_body}\n\n{menu}".strip()
    else:
        body = menu
    await send_whatsapp_message(to=phone_number, body=body)


async def _send_returning_user_reentry_prompt(session: Session, phone_number: str) -> None:
    if session.flow_state.get("returning_reentry_in_progress"):
        print(f"[WhatsApp] Returning reentry already in progress for {phone_number}")
        return
    session.flow_state["returning_reentry_in_progress"] = True
    session.flow_state["existing_user_flow_started"] = True
    await save_session(session)
    try:
        greeting = _returning_user_greeting_text(session)
        session.add_message(MessageRole.ASSISTANT, greeting)
        await save_session(session)
        await supabase_store.upsert_session_log(session)
        await send_whatsapp_message(to=phone_number, body=greeting)
        await asyncio.sleep(1.5)
        await _send_returning_location_prompt(session, phone_number)
    finally:
        session.flow_state.pop("returning_reentry_in_progress", None)
        await save_session(session)


async def _send_willing_to_create_project_prompt(session: Session, phone_number: str) -> None:
    _clear_returning_user_prompt_state(session)
    session.flow_state.pop(RETURNING_MCQ_SENT_FIELD, None)
    await _hydrate_returning_profile_from_tatva(session, force=True)
    step = position_session_for_project_decision(session)
    _touch_session_activity(session)
    if not step:
        body = WILLING_TO_CREATE_PROJECT_FALLBACK
        session.add_message(MessageRole.ASSISTANT, body)
        await save_session(session)
        await supabase_store.upsert_session_log(session)
        await send_whatsapp_message(to=phone_number, body=body)
        return
    outbound = dict(step)
    outbound["twilio_list_prompt"] = str(
        step.get("twilio_list_prompt") or step.get("prompt") or ""
    ).strip()
    await _send_returning_interactive_mcq_once(session, phone_number, outbound)


def _in_file_upload_flow(session: Session) -> bool:
    return bool(
        edit_flow.awaiting_file_upload(session)
        or hybrid_flow.pending_file_upload(session)
        or hybrid_flow.has_pending_file_upload_step(session)
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
    else:
        hybrid_flow.prepare_for_incoming_file_upload(session)
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
    is_final_review = (
        outbound_step
        and outbound_step.get("type") == "mcq"
        and outbound_step.get("field") == "__final_review__"
    )
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
        if is_final_review:
            parts = [p for p in ((file_ack or "").strip(), follow_up) if p]
            context_body = "\n\n".join(parts)
        else:
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
    async with _session_lock(session_id):
        session = await get_session(session_id)
        if not session:
            return
        if session.flow_state.get("media_upload_batch_version") != batch_version:
            return
        if session.flow_state.get("media_upload_follow_up_sent") == batch_version:
            return

        hybrid_flow.init_flow(session)
        hybrid_flow.prepare_for_incoming_file_upload(session)
        early_file_upload_complete = session.flow_state.pop("early_file_upload_complete", False)
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
            ask_for_more=not awaiting_additional and not early_file_upload_complete,
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
async def whatsapp_webhook(request: Request):
    # Twilio signs every POST field — pass the full form body, not a hand-picked subset.
    raw_form = await request.form()
    form_params = {k: str(v) for k, v in raw_form.items()}

    From = form_params.get("From", "")
    Body = form_params.get("Body", "")
    MessageSid = form_params.get("MessageSid", "")
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
        asyncio.create_task(send_say_hi_prompt(phone_number))
        print(f"[WhatsApp] RESTART45 reset OK for {From}")
        return Response(content=twiml_response(reset_msg), media_type="application/xml")

    # Process before returning TwiML — background tasks on Render free tier can be
    # cut off before outbound Twilio sends complete, which looks like "no reply".
    await handle_whatsapp_message_bg(
        session_id,
        phone_number,
        user_message,
        NumMedia,
        media_items,
        ButtonText or "",
        ButtonPayload or "",
        resolved_list_id,
        MessageSid or "",
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
    message_sid: str = "",
):
    async with _session_lock(session_id):
        try:
            if not await claim_inbound_message(
                message_sid,
                phone_number=phone_number,
                user_message=user_message,
            ):
                print(
                    f"[WhatsApp] Duplicate inbound skipped: sid={message_sid!r} "
                    f"from={phone_number!r} body={user_message!r}"
                )
                return
            await _handle_whatsapp_message_impl(
                session_id, phone_number, user_message, num_media, media_items or [],
                button_text, button_payload, list_id, message_sid,
            )
        except Exception as e:
            import traceback
            print(f"[WhatsApp] Handler error: {e}")
            traceback.print_exc()
            await log_event("API_ERROR", session_id=session_id,
                            data={"error": str(e), "phase": "whatsapp_handler"})
            try:
                await send_whatsapp_message(
                    to=phone_number,
                    body=(
                        "Sorry, something went wrong on our side. "
                        "Please reply *Hi* or tap *Say Hi* to start again."
                    ),
                )
            except Exception:
                pass


async def _handle_whatsapp_message_impl(
    session_id: str,
    phone_number: str,
    user_message: str,
    num_media: int = 0,
    media_items: list[tuple[str, str]] | None = None,
    button_text: str = "",
    button_payload: str = "",
    list_id: str = "",
    message_sid: str = "",
):
    media_items = media_items or []
    session = await get_session(session_id)

    if session and (user_message or num_media > 0):
        _touch_session_activity(session)

    # In-progress chat idle > N minutes — reset; registered users get the welcome-back flow.
    if session and (user_message or num_media > 0) and is_session_idle_expired(session):
        stale_session = session
        print(f"[WhatsApp] Idle timeout reset for {phone_number} (>{_settings.session_idle_timeout_minutes}m)")
        await start_fresh_session(session_id, phone_number, reason="idle_timeout")
        session = await get_session(session_id)
        if user_message and await _try_registered_user_greeting_restart(
            session, session_id, phone_number, user_message, message_sid=message_sid
        ):
            return
        reply = build_idle_fresh_start_reply(stale_session, user_message)
        se.start_client_stage(session)
        session.add_message(MessageRole.ASSISTANT, reply)
        await save_session(session)
        await supabase_store.upsert_session_log(session)
        await send_whatsapp_message(to=phone_number, body=reply)
        return

    # Registered user said hi/hello — always welcome back by name (even from stale final review).
    if user_message and await _try_registered_user_greeting_restart(
        session, session_id, phone_number, user_message, message_sid=message_sid
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
        if session:
            session.flow_state["awaiting_say_hi"] = True
            await save_session(session)

    # Say Hi gate — new WhatsApp users must tap the template (sends "hi") before chat starts.
    if session and session.flow_state.get("awaiting_say_hi"):
        if hybrid_flow.accepts_say_hi_start(
            list_id=list_id,
            button_payload=button_payload,
            button_text=button_text,
            user_message=user_message,
        ):
            session.add_message(MessageRole.USER, hybrid_flow.SAY_HI_PAYLOAD)
            _touch_session_activity(session)
            await save_session(session)
            await _start_chat_after_say_hi(session, phone_number)
            return
        if user_message or num_media > 0:
            print(f"[WhatsApp] Awaiting Say Hi tap for {phone_number} msg={user_message!r}")
            await _send_say_hi_gate(session, phone_number, remind=bool(user_message))
            return

    # Greeting mid-flow (Hi bro, Namaste, etc.) — restart for new users only; registered users handled above.
    if (
        session
        and user_message
        and not session.flow_state.get("project_declined")
        and is_greeting_message(user_message)
        and had_conversation_progress(session)
        and not _is_registered_returning_user(session)
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
        session.flow_state["awaiting_say_hi"] = True
        await save_session(session)
        if hybrid_flow.accepts_say_hi_start(
            list_id=list_id,
            button_payload=button_payload,
            button_text=button_text,
            user_message=user_message,
        ):
            session.add_message(MessageRole.USER, hybrid_flow.SAY_HI_PAYLOAD)
            await save_session(session)
            await _start_chat_after_say_hi(session, phone_number)
            return
        await _send_say_hi_gate(session, phone_number, remind=bool(user_message))
        return

    # Media upload handling (stage 9 — attachments, or edit-details file update)
    if num_media > 0 and media_items:
        session = await get_session(session_id) or session
        hybrid_flow.init_flow(session)
        saved_any = False
        for media_url, media_content_type in media_items:
            meta = await save_attachment(session, media_url, media_content_type)
            if meta:
                saved_any = True
        if saved_any:
            hybrid_flow.prepare_for_incoming_file_upload(session)
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

    if session.flow_state.get("awaiting_returning_location_decision"):
        choice = parse_returning_location_choice(
            user_message,
            list_id=list_id,
            button_payload=button_payload,
            button_text=button_text,
            session=session,
        )
        if choice is None:
            if not (user_message or list_id or button_payload or button_text):
                return
            hint = (
                "Please tap *Choose option* above and pick one of your saved locations, "
                "or *Other address*."
                if get_cached_user_addresses(session)
                else "Please tap *Choose option* above and pick *Yes, this is correct* or *Other address*."
            )
            await send_whatsapp_message(to=phone_number, body=hint)
            return
        session.flow_state.pop("awaiting_returning_location_decision", None)
        _set_returning_user_phase(session, "")
        apply_returning_location_choice(session, choice)
        await _send_willing_to_create_project_prompt(session, phone_number)
        return

    if not user_message:
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
            return
        if chosen in {"client_name", "email", "property_location"}:
            session.flow_state.pop("awaiting_returning_profile_field", None)
            session.flow_state["awaiting_returning_profile_value"] = True
            session.flow_state["returning_profile_edit_field"] = chosen
            _set_returning_user_phase(session, "profile_value")
            if chosen == "client_name":
                prompt = "Please type your name."
            elif chosen == "email":
                prompt = "Please type your Gmail address (or reply skip)."
            else:
                prompt = "Where is your property located? (City, Locality)"
            await save_session(session)
            await supabase_store.upsert_session_log(session)
            await send_whatsapp_message(to=phone_number, body=prompt)
            return
        await _send_returning_plain_mcq(
            phone_number,
            _returning_profile_field_step(),
            context_body="Please choose *Name*, *Email*, *Property location*, or *Continue*.",
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
        elif field == "property_location":
            if not text:
                await send_whatsapp_message(
                    to=phone_number,
                    body="Please type your property location (City, Locality).",
                )
                return
            se.mark_field_validated(session, "property_location", text)
        session.flow_state.pop("awaiting_returning_profile_value", None)
        session.flow_state.pop("returning_profile_edit_field", None)
        session.flow_state["awaiting_returning_profile_field"] = True
        _set_returning_user_phase(session, "profile_field")
        await save_session(session)
        await supabase_store.upsert_session_log(session)
        await _send_returning_plain_mcq(
            phone_number,
            _returning_profile_field_step(),
            context_body="Updated successfully.",
        )
        return

    # Registered user already finished the edit prompt — do not restart it from the controller.
    if (
        session.flow_state.get("returning_edit_flow_complete")
        and is_greeting_message(user_message)
    ):
        step = hybrid_flow.get_current_step(session)
        hold = "Please continue with the current question below."
        if step:
            hold += f"\n\n{hybrid_flow.format_step_message(step, include_stage=False)}"
        await send_whatsapp_message(to=phone_number, body=hold)
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

    await supabase_store.upsert_session_log(agent_response.session)

    session_out = agent_response.session
    _clear_returning_mcq_sent_if_complete(session_out)

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
        tatva_attachments = agent_response.session.flow_state.get("tatva_enquiry_attachments")
        if isinstance(tatva_attachments, list) and tatva_attachments:
            await send_whatsapp_attachment_cta_links(phone_number, tatva_attachments)
        follow_up = (agent_response.follow_up_text or "").strip()
        if follow_up:
            await send_whatsapp_message(to=phone_number, body=follow_up)
        await log_event(
            "CONVERSATION_ENDED",
            session_id=session_id,
            data={"reason": "enquiry_submitted", "channel": "whatsapp"},
        )
        await clear_cached_session(session_id, reason="enquiry_submitted")
        return

    await save_session(agent_response.session)

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

    pending_mcq = session_out.flow_state.pop("pending_outbound_mcq", None)
    if pending_mcq:
        from backend.agents.chat.twilio_client import RETURNING_MCQ_FIELDS
        pending_field = str(pending_mcq.get("field") or "")
        if pending_field in RETURNING_MCQ_FIELDS and (
            session_out.flow_state.get("returning_edit_flow_complete")
            or session_out.flow_state.get("existing_user_flow_started")
        ):
            # Re-show location list after an invalid reply (full addresses + short labels).
            if not (
                pending_field == RETURNING_LOCATION_FIELD
                and session_out.flow_state.get("awaiting_returning_location_decision")
            ):
                pending_mcq = None
    if pending_mcq:
        context_body = (reply or "").strip()
        if str(pending_mcq.get("field") or "") == RETURNING_LOCATION_FIELD:
            address_context = str(pending_mcq.get("prompt") or "").strip()
            if address_context:
                context_body = f"{context_body}\n\n{address_context}".strip()
        await send_context_then_mcq_list(phone_number, context_body, pending_mcq)
        return

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
    if _should_skip_duplicate_returning_outbound(session_out, outbound_step):
        transition = _strip_outbound_prompt_from_reply(reply, outbound_step)
        if transition:
            await send_whatsapp_message(to=phone_number, body=transition)
        await save_session(session_out)
        return

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

"""
Stage-locked qualification flow — strict validation, fuzzy MCQ matching.
"""
from __future__ import annotations
from typing import Any, Optional

from backend.schemas.session import Session, ConversationStage
from backend.intelligence import qualification_builder as qb
from backend.intelligence import stage_engine as se
from backend.intelligence.input_normalizer import match_mcq_option

OTHER_VALUE = "__other__"

TEXT_ONLY_FIELDS = frozenset({
    "client_name", "city", "property_location", "email",
    "req_functional_needs", "req_inspiration_notes", "special_notes_extra",
})

_SKIP_WORDS = frozenset({"skip", "none", "nil", "-"})
_DETAILS_UNAVAILABLE_PHRASES = (
    "i don't have",
    "i dont have",
    "don't have",
    "dont have",
    "no data",
    "not sure",
    "don't know",
    "dont know",
    "no idea",
)

STAGE_BRIDGES = {
    "client_details": "Perfect ✨ Let us start with a few quick details.",
    "service_selection": "Great. Please choose the TatvaOps service you need.",
    "service_questionnaire": "Thanks for sharing. Let us understand your requirements.",
}

SERVICE_SELECTION_TRANSITION = "Got it. Let us continue."

PROJECT_DECLINED_FAREWELL = (
    "Thank you for sharing your details with TatvaOps.\n\n"
    "We understand you are not looking to start a project at this time. "
    "Whenever you are ready, we will be glad to assist you.\n\n"
    "Wishing you all the best.\n\n"
    "If you would like to start a new enquiry, please restart after 5 minutes."
)


def _is_project_declined(value: Any) -> bool:
    return str(value or "").strip().lower() in ("no", "n")


def _sounds_like_unavailable_detail(text: str) -> bool:
    low = (text or "").strip().lower()
    if not low:
        return False
    return any(phrase in low for phrase in _DETAILS_UNAVAILABLE_PHRASES)


def init_flow(session: Session) -> None:
    se.reconcile_session(session)
    phone = (session.phone_number or "").strip()
    if phone.lower().startswith("whatsapp:"):
        phone = phone.split(":", 1)[-1]
    if phone and "phone_number" not in session.completed_fields:
        se.mark_field_validated(session, "phone_number", phone.strip())


def _steps_in_current_stage(session: Session) -> list[dict]:
    stage = se.fs_current_stage(session)
    if stage == "final_review":
        return []
    return qb.get_steps_for_stage(session, stage)


def _field_pending(session: Session, step: dict) -> bool:
    field = step.get("field")
    return bool(field and not se.field_is_complete(session, field))


def _finalize_step(step: Optional[dict]) -> Optional[dict]:
    if not step:
        return None
    from backend.agents.chat.twilio_client import enrich_whatsapp_mcq_step
    return enrich_whatsapp_mcq_step(step)


def get_current_step(session: Session) -> Optional[dict]:
    se.reconcile_session(session)
    stage = se.fs_current_stage(session)
    if stage == "final_review":
        se.set_current_question(session, None)
        return None

    steps = _steps_in_current_stage(session)
    if not steps:
        return None

    step_id = session.flow_state.get("current_step_id")
    if step_id:
        for i, s in enumerate(steps):
            if s["id"] == step_id:
                if _field_pending(session, s):
                    se.set_current_question(session, s.get("field"))
                    return _finalize_step(s)
                for nxt in steps[i + 1:]:
                    if _field_pending(session, nxt):
                        session.flow_state["current_step_id"] = nxt["id"]
                        se.set_current_question(session, nxt.get("field"))
                        return _finalize_step(nxt)
                se.set_current_question(session, None)
                return None

    for s in steps:
        if _field_pending(session, s):
            session.flow_state["current_step_id"] = s["id"]
            se.set_current_question(session, s.get("field"))
            return _finalize_step(s)

    session.flow_state.pop("current_step_id", None)
    se.set_current_question(session, None)
    return None


def _complete_field(session: Session, field: str, value: Any) -> Optional[str]:
    if not se.mark_field_validated(session, field, value):
        step = get_current_step(session)
        if step and step.get("field") == field:
            return format_step_message(step) + "\n\nPlease provide a valid answer."
        return "Please provide a valid answer before we continue."

    answers = session.flow_state.setdefault("answers", {})
    answers[field] = value
    completed_q = session.flow_state.setdefault("completed_questions", [])
    if field not in completed_q and se.fs_current_stage(session) == "service_questionnaire":
        completed_q.append(field)
    required_q = session.flow_state.get("service_questionnaire_required_fields") or [
        "service_q1", "service_q2", "service_q3", "service_q4", "attachments",
    ]
    session.flow_state["pending_questions"] = [
        q for q in required_q if q not in completed_q and not se.field_is_complete(session, q)
    ]

    if field == "willing_to_create_project" and _is_project_declined(value):
        return _end_after_project_declined(session)

    session.flow_state.pop("current_step_id", None)
    se.maybe_advance_current_stage(session)

    if se.can_enter_final_review(session) and se.fs_current_stage(session) == "final_review":
        return _enter_final_review(session)

    return _next_step_message(session)


def _end_after_project_declined(session: Session) -> str:
    """Close the chat politely when the client is not ready to start a project."""
    session.flow_state.pop("current_step_id", None)
    se.mark_stage_complete(session, "client_details")
    session.flow_state["project_declined"] = True
    session.flow_state["conversation_ended"] = True
    session.flow_state["current_stage"] = "client_details"
    se.set_current_question(session, None)
    return PROJECT_DECLINED_FAREWELL


def _is_other_option(opt: dict) -> bool:
    val = str(opt.get("value", "")).lower()
    label = str(opt.get("label", "")).lower()
    return val == OTHER_VALUE or label == "other" or label.startswith("other ")


def is_text_only_step(step: dict) -> bool:
    if step.get("type") == "descriptive":
        return True
    return step.get("field") in TEXT_ONLY_FIELDS


def format_mcq_message(step: dict) -> str:
    from backend.agents.chat.twilio_client import mcq_uses_interactive_delivery

    if mcq_uses_interactive_delivery(step):
        return step.get("prompt", "Please choose one option.")
    options = step.get("options", [])
    lines = [step.get("prompt", "Please choose:"), ""]
    for opt in options:
        lines.append(f"• {opt['label']}")
    if any(_is_other_option(o) for o in options):
        lines.append("")
        lines.append("If you choose *Other*, type your specific requirement next.")
    return "\n".join(lines)


def format_multi_select_message(step: dict) -> str:
    return format_mcq_message(step)


def invalid_email_reply() -> str:
    return (
        "That doesn't look like a valid Gmail address.\n\n"
        "Please enter an email ending with *@gmail.com* (e.g. name@gmail.com), "
        "or reply *skip* to continue without email."
    )


def invalid_choice_reply(step: dict) -> str:
    """
    Politely reject input that does not match MCQ options and re-ask the current question.
    Does not repeat stage-bridge intros — user stays on the same step.
    """
    apology = "Sorry, I didn't quite get that."
    hint = "Please choose one of the options below, or reply with the option number or name."
    stype = step.get("type")
    if stype == "multi_select":
        hint = "Please reply with one or more option numbers or names from the list below."

    from backend.agents.chat.twilio_client import mcq_uses_interactive_delivery

    if mcq_uses_interactive_delivery(step):
        prompt = str(step.get("prompt") or "Please choose one option.").strip()
        return f"{apology}\n\n{prompt}\n\n{hint}"

    question_body = format_step_message(step, include_stage=False)
    return f"{apology}\n\n{question_body}\n\n{hint}"


def format_step_message(step: dict, *, include_stage: bool = True) -> str:
    parts: list[str] = []
    if include_stage:
        bridge = STAGE_BRIDGES.get(step.get("stage", ""))
        if bridge:
            parts.extend([bridge, ""])
    if is_text_only_step(step):
        body = step.get("prompt", "Please type your answer.")
        if step.get("optional") and "skip" not in body.lower():
            body += "\n\n(Reply *skip* if not applicable.)"
    elif step.get("type") == "mcq":
        body = format_mcq_message(step)
    elif step.get("type") == "multi_select":
        body = format_multi_select_message(step)
    elif step.get("type") == "file_request":
        body = step.get("prompt", "") + "\n\n(Reply *skip* if nothing to upload.)"
    else:
        body = step.get("prompt", "Please share your answer.")
    parts.append(body)
    return "\n".join(parts)


def _resolve_mcq_choice(step: dict, chosen: dict) -> dict[str, Any]:
    field = step["field"]
    if _is_other_option(chosen):
        return {"__other__": field}
    return {field: chosen.get("value", chosen["label"])}


def _is_interactive_mcq_tap(
    *,
    list_id: Optional[str] = None,
    button_text: Optional[str] = None,
    button_payload: Optional[str] = None,
) -> bool:
    return bool((list_id or "").strip() or (button_payload or "").strip() or (button_text or "").strip())


def _collect_flow_mcq_steps(session: Session) -> list[dict]:
    """MCQ steps from earlier stages still visible as WhatsApp list pickers in chat."""
    steps: list[dict] = []
    for step in qb.build_client_details_steps():
        if step.get("type") in ("mcq", "multi_select"):
            steps.append(step)
    from backend.intelligence.nova_router import get_service_selection_outbound_step

    if session.service_category or se.needs_service_selection(session):
        svc_step = get_service_selection_outbound_step(session)
        if svc_step and svc_step.get("type") in ("mcq", "multi_select"):
            steps.append(svc_step)
    if session.service_category:
        steps.extend(qb.get_service_questionnaire_steps(session))
    return steps


def _option_matches_list_id(opt: dict, list_id: str) -> bool:
    lid = list_id.strip()
    if not lid:
        return False
    return str(opt.get("value")) == lid or str(opt.get("label")) == lid


def find_step_for_interactive_selection(
    session: Session,
    *,
    list_id: Optional[str] = None,
    button_text: Optional[str] = None,
    button_payload: Optional[str] = None,
    user_message: str = "",
) -> Optional[dict]:
    """
    Map a WhatsApp list/button tap to the question step it came from.
    list_id is authoritative when present (row value from the tapped message).
    """
    lid = (list_id or "").strip()
    tap = (button_text or button_payload or "").strip()
    text = (user_message or "").strip()
    steps = _collect_flow_mcq_steps(session)

    if lid:
        for step in steps:
            for opt in step.get("options", []):
                if _option_matches_list_id(opt, lid):
                    return step
        return None

    candidates: list[dict] = []
    for probe in (tap, text):
        if not probe:
            continue
        for step in steps:
            if step.get("type") not in ("mcq", "multi_select"):
                continue
            if match_mcq_option(probe, step.get("options", [])):
                candidates.append(step)
        if candidates:
            break

    if not candidates:
        return None
    if len(candidates) == 1:
        return candidates[0]

    current = get_current_step(session)
    current_field = str((current or {}).get("field") or "")
    for step in candidates:
        if str(step.get("field") or "") == current_field:
            return step
    for step in candidates:
        if se.field_is_complete(session, str(step.get("field") or "")):
            return step
    return candidates[0]


def is_stale_mcq_selection(session: Session, matched_step: dict) -> bool:
    """True when the tap targets a question that is no longer the active step."""
    field = str(matched_step.get("field") or "")
    if not field:
        return False
    current = get_current_step(session)
    current_field = str((current or {}).get("field") or "")
    if current_field and current_field == field:
        return False
    if se.field_is_complete(session, field):
        return True
    return bool(current_field and current_field != field)


def stale_mcq_reply(session: Session) -> str:
    """User tapped an old WhatsApp list — options cannot be disabled in the chat UI."""
    msg = (
        "You've already answered that question, so that option can't be changed here.\n\n"
        "Please continue with the current question below."
    )
    current = get_current_step(session)
    if current:
        prompt = str(current.get("prompt") or "").strip()
        if prompt:
            first_line = prompt.split("\n")[0].strip()
            if first_line:
                msg += f"\n\n*{first_line}*"
    return msg


def check_stale_interactive_selection(
    session: Session,
    *,
    list_id: Optional[str] = None,
    button_text: Optional[str] = None,
    button_payload: Optional[str] = None,
    user_message: str = "",
    allowed_field: Optional[str] = None,
) -> Optional[str]:
    """
    Return a user-facing reply when an interactive tap targets a completed/out-of-order question.
    allowed_field: when editing one field, re-taps on that same question remain valid.
    """
    if not _is_interactive_mcq_tap(
        list_id=list_id, button_text=button_text, button_payload=button_payload,
    ):
        return None
    matched = find_step_for_interactive_selection(
        session,
        list_id=list_id,
        button_text=button_text,
        button_payload=button_payload,
        user_message=user_message,
    )
    if not matched:
        return None
    matched_field = str(matched.get("field") or "")
    if matched_field == "service_category" and se.needs_service_selection(session):
        return None
    from backend.agents.chat.twilio_client import RETURNING_MCQ_FIELDS
    if matched_field in RETURNING_MCQ_FIELDS and session.flow_state.get("returning_edit_flow_complete"):
        return None
    if allowed_field and matched_field == allowed_field:
        return None
    if is_stale_mcq_selection(session, matched):
        return stale_mcq_reply(session)
    return None


def try_resolve_mcq(
    session: Session,
    user_message: str,
    *,
    button_text: Optional[str] = None,
    button_payload: Optional[str] = None,
    list_id: Optional[str] = None,
) -> Optional[dict[str, Any]]:
    step = get_current_step(session)
    if not step or step.get("type") not in ("mcq", "multi_select"):
        return None
    options = step.get("options", [])

    if list_id:
        for opt in options:
            if str(opt.get("value")) == list_id or str(opt.get("label")) == list_id:
                return _resolve_mcq_choice(step, opt)

    tap = (button_text or button_payload or "").strip()
    if tap:
        matched = match_mcq_option(tap, options)
        if matched:
            return _resolve_mcq_choice(step, matched)

    text = user_message.strip()
    if step.get("type") == "multi_select":
        return _resolve_multi_select(step, text)

    matched = match_mcq_option(text, options)
    return _resolve_mcq_choice(step, matched) if matched else None


def _resolve_multi_select(step: dict, text: str) -> Optional[dict[str, Any]]:
    options = step.get("options", [])
    tokens = [t.strip() for t in text.replace("and", ",").replace(" ", ",").split(",") if t.strip()]
    if not tokens:
        return None
    chosen_values: list[str] = []
    has_other = False
    for tok in tokens:
        if tok.isdigit():
            idx = int(tok) - 1
            if 0 <= idx < len(options):
                opt = options[idx]
                if _is_other_option(opt):
                    has_other = True
                else:
                    chosen_values.append(str(opt.get("value", opt["label"])))
        else:
            matched = match_mcq_option(tok, options)
            if matched:
                if _is_other_option(matched):
                    has_other = True
                else:
                    chosen_values.append(str(matched.get("value", matched["label"])))
    if has_other and not chosen_values:
        return {"__other__": step["field"]}
    if not chosen_values:
        return None
    return {step["field"]: chosen_values}


def has_active_flow(session: Session) -> bool:
    if session.summary_generated:
        return False
    se.reconcile_session(session)
    if se.fs_current_stage(session) == "final_review":
        return bool(session.flow_state.get("awaiting_other_field"))
    if not se.is_collecting_qualification(session):
        return False
    return get_current_step(session) is not None or bool(session.flow_state.get("awaiting_other_field"))


def is_flow_complete(session: Session) -> bool:
    return se.can_enter_final_review(session) and se.fs_current_stage(session) == "final_review"


def process_hybrid_turn(
    session: Session,
    user_message: str,
    *,
    button_text: Optional[str] = None,
    button_payload: Optional[str] = None,
    list_id: Optional[str] = None,
) -> tuple[Optional[str], bool]:
    se.reconcile_session(session)

    raw_text = (user_message or "").strip()
    normalized_text = raw_text.lstrip("\\/").strip()

    awaiting = session.flow_state.get("awaiting_other_field")
    if awaiting:
        text = normalized_text
        if not text:
            return ("Please type your answer.", True)
        session.flow_state.pop("awaiting_other_field", None)
        msg = _complete_field(session, awaiting, text)
        return (msg or _prompt_continue(session), True)

    stale_reply = check_stale_interactive_selection(
        session,
        list_id=list_id,
        button_text=button_text,
        button_payload=button_payload,
        user_message=normalized_text,
    )
    if stale_reply:
        return (stale_reply, True)

    step = get_current_step(session)
    if not step:
        if se.can_enter_final_review(session):
            return (_enter_final_review(session), True)
        se.reconcile_session(session)
        step = get_current_step(session)
        if step:
            return (format_step_message(step), True)
        return (
            "Let's continue your qualification. Reply *RESTART45* if you'd like to start over.",
            True,
        )

    stype = step.get("type")
    field = step.get("field", "")

    if stype in ("mcq", "multi_select"):
        resolved = try_resolve_mcq(
            session, normalized_text,
            button_text=button_text, button_payload=button_payload, list_id=list_id,
        )
        if resolved and "__other__" in resolved:
            session.flow_state["awaiting_other_field"] = resolved["__other__"]
            return ("You selected *Other*. Please type your answer.", True)
        if resolved:
            fn = next(iter(resolved))
            msg = _complete_field(session, fn, resolved[fn])
            return (msg or _prompt_continue(session), True)
        return (invalid_choice_reply(step), True)

    if stype == "descriptive" or is_text_only_step(step):
        text = (normalized_text or button_text or "").strip()
        if step.get("optional") and text.lower() in _SKIP_WORDS:
            msg = _complete_field(session, field, "")
            return (msg or _prompt_continue(session), True)
        if text and text.lower() not in _SKIP_WORDS:
            if field == "email" and not se.is_valid_gmail_address(text):
                return (invalid_email_reply(), True)
            msg = _complete_field(session, field, text)
            if (
                msg
                and stype == "descriptive"
                and field.startswith("service_q")
                and _sounds_like_unavailable_detail(text)
            ):
                msg = f"That's absolutely fine.\n\n{msg}"
            return (msg or _prompt_continue(session), True)
        return (format_step_message(step), True)

    if stype == "file_request":
        upload_field = field or "attachments"
        if normalized_text.lower() in _SKIP_WORDS | {"skip", "later"}:
            msg = _complete_field(session, upload_field, "skipped")
            return (msg or _prompt_continue(session), True)
        return (format_step_message(step), True)

    return (None, False)


def _prompt_continue(session: Session) -> str:
    step = get_current_step(session)
    if step:
        return format_step_message(step)
    if se.can_enter_final_review(session):
        return _enter_final_review(session)
    return "Got it. Let us continue."


def _enter_final_review(session: Session) -> str:
    if not se.enter_final_review(session):
        se.reconcile_session(session)
        step = get_current_step(session)
        if step:
            return format_step_message(step)
        return "We still need a few details before your summary. Please answer the question above."
    return qb.format_final_review(session)


def _next_step_message(session: Session) -> Optional[str]:
    if se.fs_current_stage(session) == "final_review":
        return None
    step = get_current_step(session)
    if not step:
        stage = se.fs_current_stage(session)
        if se.is_stage_complete(session, stage):
            se.maybe_advance_current_stage(session)
            if se.fs_current_stage(session) == "final_review" and se.can_enter_final_review(session):
                return _enter_final_review(session)
            step = get_current_step(session)
        if not step:
            if se.fs_current_stage(session) == "service_selection":
                return SERVICE_SELECTION_TRANSITION
            return None
    last = session.flow_state.get("last_stage_shown")
    stage = step.get("stage")
    show = stage != last
    if show and stage:
        session.flow_state["last_stage_shown"] = stage
    return format_step_message(step, include_stage=show)


def append_first_step_to_handoff(session: Session, handoff_text: str) -> str:
    step = get_current_step(session)
    if not step:
        return handoff_text
    if step.get("type") == "mcq":
        # Enrich first so dynamic list metadata is considered before appending plain text.
        from backend.agents.chat.twilio_client import enrich_whatsapp_mcq_step
        enriched = enrich_whatsapp_mcq_step(step)
        if enriched and (enriched.get("twilio_content_sid") or enriched.get("use_dynamic_list")):
            # Keep handoff clean; interactive list will be sent as the next message payload.
            return handoff_text
    if step.get("stage"):
        session.flow_state["last_stage_shown"] = step["stage"]
    return f"{handoff_text}\n\n{format_step_message(step)}"


def eva_intro_text() -> str:
    return (
        "Hi 👋\n\n"
        "I'm EVA, your TatvaOps assistant.\n\n"
        "TatvaOps helps homeowners build, renovate, and upgrade their homes with trusted experts, transparent workflows, and real-time project support.\n\n"
        "I’ll guide you step-by-step and connect you with the right specialist for your project ✨\n\n"
    )


SAY_HI_PAYLOAD = "hi"
SAY_HI_FIELD = "__say_hi__"


def say_hi_welcome_text(*, remind: bool = False) -> str:
    """Short welcome shown before EVA intro — user must tap Say Hi to continue."""
    base = (
        "Welcome to TatvaOps! 👋\n\n"
        "Tap *Say Hi* below to start your conversation with EVA, "
        "your home project assistant."
    )
    if remind:
        return (
            "Please tap *Say Hi* below to get started.\n\n"
            "Typed greetings like hello or bonjour won't start the chat — "
            "use the button so we can connect you correctly."
        )
    return base


def say_hi_prompt_step() -> dict[str, Any]:
    """Single-option WhatsApp list for the initial Say Hi tap."""
    return {
        "id": "say_hi",
        "type": "mcq",
        "field": SAY_HI_FIELD,
        "twilio_list_prompt": "Tap below to get started.",
        "prompt": say_hi_welcome_text(),
        "options": [{"label": "Say Hi 👋", "value": SAY_HI_PAYLOAD}],
        "require_content_variables": True,
    }


def is_say_hi_tap(
    *,
    list_id: str = "",
    button_payload: str = "",
    button_text: str = "",
    user_message: str = "",
) -> bool:
    """True only for the Say Hi template tap — not typed hello/bonjour/etc."""
    for raw in (list_id, button_payload):
        if (raw or "").strip().lower() == SAY_HI_PAYLOAD:
            return True
    btn = (button_text or "").strip().lower()
    if btn.startswith("say hi"):
        return True
    return False


def first_client_message() -> str:
    steps = qb.build_client_details_steps()
    intro = eva_intro_text()
    if steps:
        # EVA intro already welcomes the user — skip the client_details stage bridge here.
        return intro + format_step_message(steps[0], include_stage=False)
    return intro


def advance_step(session: Session) -> None:
    """Legacy alias — advance current stage if complete."""
    se.maybe_advance_current_stage(session)


def resolve_file_upload_field(session: Session) -> str:
    """Field name for the questionnaire file-upload step (attachments or file_order_N)."""
    step = get_current_step(session)
    if step and step.get("type") == "file_request":
        return str(step.get("field") or "attachments")
    for s in qb.get_service_questionnaire_steps(session):
        if s.get("type") == "file_request":
            return str(s.get("field") or "attachments")
    return "attachments"


def attachment_count(session: Session) -> int:
    return len(session.attachments or [])


def attachment_upload_value(session: Session) -> str:
    count = attachment_count(session)
    if count <= 0:
        return "skipped"
    if count == 1:
        return "1 file uploaded"
    return f"{count} files uploaded"


def format_attachment_review_line(session: Session) -> str:
    """Client-facing file count for final review / summary."""
    count = attachment_count(session)
    if count <= 0:
        field = resolve_file_upload_field(session)
        raw = str(session.extracted_fields.get(field) or "").strip().lower()
        if raw in ("skipped", "skip", "none", ""):
            return "No files uploaded"
    if count == 1:
        return "1 file uploaded"
    return f"{count} files uploaded"


def sync_attachment_fields(session: Session, *, complete_step: bool = True) -> None:
    """Align stored file-step answers with session.attachments (source of truth)."""
    se.reconcile_session(session)
    field = resolve_file_upload_field(session)
    count = attachment_count(session)
    existing = str(session.extracted_fields.get(field) or "").strip().lower()
    if count <= 0:
        if field not in session.completed_fields and not existing:
            return
        if existing in ("skipped", "skip", "none", ""):
            return
    value = attachment_upload_value(session)
    if field in session.completed_fields or session.extracted_fields.get(field) or count > 0:
        if complete_step:
            se.mark_field_validated(session, field, value)
        else:
            session.extracted_fields[field] = value
            if field in session.completed_fields:
                session.completed_fields.remove(field)


def file_upload_ack_message(session: Session) -> str:
    count = attachment_count(session)
    if count > 1:
        return f"Thank you! We received your {count} files."
    return "Thank you! We received your file."


def refresh_attachment_field_count(session: Session) -> None:
    """Update stored file-step value after additional uploads in the same batch."""
    holding = bool(
        session.flow_state.get("awaiting_more_upload_decision")
        or session.flow_state.get("awaiting_additional_file_upload")
    )
    sync_attachment_fields(session, complete_step=not holding)


def additional_file_upload_prompt() -> str:
    """Short nudge when the user chose to upload more files — no stage bridge or service prompt."""
    return "Please upload your file(s). You can send multiple files."


def strip_post_upload_follow_up(session: Session, text: str) -> str:
    """Remove file-upload step copy that must not repeat after files were received."""
    cleaned = (text or "").strip()
    if not cleaned:
        return ""

    bridge = STAGE_BRIDGES.get("service_questionnaire", "")
    if bridge:
        cleaned = cleaned.replace(bridge, "").strip()

    skip_hints = (
        "(Reply *skip* if nothing to upload.)",
        "(Reply skip if nothing to upload.)",
    )
    for step in qb.get_service_questionnaire_steps(session):
        if step.get("type") != "file_request":
            continue
        for chunk in (
            str(step.get("prompt") or "").strip(),
            format_step_message(step, include_stage=False),
            format_step_message(step, include_stage=True),
        ):
            if chunk and chunk in cleaned:
                cleaned = cleaned.replace(chunk, "").strip()
    for hint in skip_hints:
        cleaned = cleaned.replace(hint, "").strip()

    return "\n".join(line for line in cleaned.splitlines() if line.strip()).strip()


def _force_advance_past_file_upload(session: Session) -> None:
    """Ensure the file-upload step is completed and the flow moves forward."""
    sync_attachment_fields(session, complete_step=True)
    session.flow_state.pop("current_step_id", None)
    se.maybe_advance_current_stage(session)


def complete_attachment_upload(session: Session) -> str:
    """
    Called after WhatsApp media is saved. Completes the current file step and advances.
    """
    _force_advance_past_file_upload(session)
    if se.can_enter_final_review(session):
        return _enter_final_review(session)
    step = get_current_step(session)
    if step and step.get("type") == "file_request":
        _force_advance_past_file_upload(session)
        step = get_current_step(session)
    if step and step.get("type") == "file_request":
        return ""
    msg = _next_step_message(session)
    return strip_post_upload_follow_up(session, msg or "")


def _pending_file_upload_fields(session: Session) -> list[str]:
    fields: list[str] = []
    for step in qb.get_service_questionnaire_steps(session):
        if step.get("type") != "file_request":
            continue
        field = str(step.get("field") or "attachments")
        if not se.field_is_complete(session, field):
            fields.append(field)
    return fields


def has_pending_file_upload_step(session: Session) -> bool:
    se.reconcile_session(session)
    return bool(_pending_file_upload_fields(session))


def prepare_for_incoming_file_upload(session: Session) -> None:
    """
    When the user sends media before the file-upload question (e.g. on a descriptive step),
    complete blocking text steps so the upload can finish the enquiry flow.
    """
    se.reconcile_session(session)
    if not _pending_file_upload_fields(session):
        return

    steps = qb.get_service_questionnaire_steps(session)
    file_step_ids = {str(s.get("id")) for s in steps if s.get("type") == "file_request"}
    step = get_current_step(session)
    skipped_descriptive = False
    while step and str(step.get("id")) not in file_step_ids:
        if step.get("type") != "descriptive":
            break
        field = str(step.get("field") or "")
        value = "skipped" if step.get("optional") else "Provided via attachment"
        se.mark_field_validated(session, field, value)
        session.flow_state.pop("current_step_id", None)
        skipped_descriptive = True
        se.reconcile_session(session)
        step = get_current_step(session)
    if skipped_descriptive:
        session.flow_state["early_file_upload_complete"] = True


def pending_file_upload(session: Session) -> bool:
    se.reconcile_session(session)
    if (
        session.flow_state.get("awaiting_more_upload_decision")
        or session.flow_state.get("awaiting_additional_file_upload")
    ):
        return True
    step = get_current_step(session)
    return bool(step and step.get("type") == "file_request")


def file_request_prompt(session: Session) -> Optional[str]:
    step = get_current_step(session)
    return format_step_message(step) if step and step.get("type") == "file_request" else None

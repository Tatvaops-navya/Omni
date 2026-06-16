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

    from backend.agents.chat.twilio_client import mcq_uses_interactive_delivery, format_mcq_options_display

    if mcq_uses_interactive_delivery(step):
        options_body = format_mcq_options_display(step)
        return f"{apology}\n\n{options_body}\n\n{hint}"

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


def complete_attachment_upload(session: Session) -> str:
    """
    Called after WhatsApp media is saved. Completes the current file step and advances.
    """
    se.reconcile_session(session)
    step = get_current_step(session)
    field = (step or {}).get("field") or "attachments"
    count = len(session.attachments)
    value = f"{count} file(s) uploaded" if count else "skipped"
    se.mark_field_validated(session, field, value)
    session.flow_state.pop("current_step_id", None)
    se.maybe_advance_current_stage(session)
    if se.can_enter_final_review(session):
        return _enter_final_review(session)
    step = get_current_step(session)
    if step:
        return format_step_message(step)
    return "Thank you! Your file has been saved."


def pending_file_upload(session: Session) -> bool:
    se.reconcile_session(session)
    step = get_current_step(session)
    return bool(step and step.get("type") == "file_request")


def file_request_prompt(session: Session) -> Optional[str]:
    step = get_current_step(session)
    return format_step_message(step) if step and step.get("type") == "file_request" else None

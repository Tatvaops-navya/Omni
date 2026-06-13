"""
Structured edit-details workflow after final review.
Re-asks only the selected field; preserves other answers.
"""
from __future__ import annotations

from typing import Any, Optional

from backend.schemas.session import Session, ConversationStage
from backend.schemas.service import CONSULTANT_IDS
from backend.intelligence import stage_engine as se
from backend.intelligence import qualification_builder as qb
from backend.intelligence import hybrid_flow
from backend.intelligence.input_normalizer import match_mcq_option
from backend.intelligence.nova_router import detect_service, edit_service_selection_step
from backend.schemas.service import ServiceCategory
_SKIP_WORDS = frozenset({"skip", "none", "nil", "-"})

_CLIENT_FIELDS: list[tuple[str, str]] = [
    ("client_name", "Name"),
    ("city", "City"),
    ("property_location", "Property Location"),
    ("preferred_contact_time", "Preferred Contact Time"),
    ("willing_to_create_project", "Willing to Create Project"),
    ("email", "Email"),
]

_SECTION_OPTIONS = [
    {"label": "Client Details", "value": "client_details"},
    {"label": "Project Requirements", "value": "project_requirements"},
    {"label": "Additional Notes", "value": "additional_notes"},
    {"label": "Uploaded Files", "value": "uploaded_files"},
]

_FILE_ACTION_OPTIONS = [
    {"label": "Add New File", "value": "add_new_file"},
    {"label": "Replace Existing File", "value": "replace_existing_file"},
    {"label": "Remove Existing File", "value": "remove_existing_file"},
]

_POST_EDIT_OPTIONS = [
    {"label": "Confirm & Submit", "value": "confirm_submit"},
    {"label": "Edit Again", "value": "edit_again"},
]

_FIELD_MENU_PROMPTS: dict[str, str] = {
    "client_details": "Which client detail would you like to change?",
    "project_requirements": "Which project requirement would you like to update?",
}

_SECTION_ALIASES: dict[str, str] = {
    "additional notes": "additional_notes",
    "additional note": "additional_notes",
    "notes": "additional_notes",
    "client details": "client_details",
    "client detail": "client_details",
    "service selection": "service_selection",
    "service": "service_selection",
    "project requirements": "project_requirements",
    "requirements": "project_requirements",
    "requirement": "project_requirements",
    "uploaded files": "uploaded_files",
    "files": "uploaded_files",
    "file": "uploaded_files",
    "attachments": "uploaded_files",
}


def is_active(session: Session) -> bool:
    return bool(session.flow_state.get("edit_mode"))


def awaiting_file_upload(session: Session) -> bool:
    return is_active(session) and session.flow_state.get("edit_phase") == "awaiting_upload"


def get_outbound_step(session: Session) -> Optional[dict]:
    if not is_active(session):
        return None
    return session.flow_state.get("edit_outbound_step")


def _pad_edit_mcq_for_whatsapp(step: dict) -> dict:
    """
    WhatsApp 4-row list templates need exactly 4 options.
    Pad smaller edit menus with navigation rows so list-picker works (not plain text).
    """
    field = str(step.get("field", ""))
    if not field.startswith("__edit_") or step.get("type") != "mcq":
        return step

    opts = list(step.get("options") or [])
    out = dict(step)

    # Confirm & Submit / Edit Again only — no extra navigation rows.
    if field == "__edit_post__":
        if not out.get("twilio_list_prompt"):
            prompt = str(out.get("prompt") or "").strip()
            out["twilio_list_prompt"] = prompt.split("\n")[0] if prompt else "Choose option"
        return out

    if len(opts) >= 4:
        pass
    else:
        padded = list(opts)
        if not any(o.get("value") == "back_to_sections" for o in padded):
            padded.append({
                "label": "Back to menu",
                "value": "back_to_sections",
                "whatsapp_label": "Back to menu",
            })
        while len(padded) < 4:
            padded.append({
                "label": "Back to menu",
                "value": "back_to_sections",
                "whatsapp_label": "Back to menu",
            })
        out = {**step, "options": padded[:4]}

    if not out.get("twilio_list_prompt"):
        prompt = str(out.get("prompt") or "").strip()
        out["twilio_list_prompt"] = prompt.split("\n")[0] if prompt else "Choose option"
    return out


def _return_to_section_menu(session: Session) -> tuple[str, dict, bool]:
    session.flow_state["edit_phase"] = "section"
    session.flow_state.pop("edit_section", None)
    session.flow_state.pop("edit_field", None)
    step = _section_menu_step()
    _set_outbound_step(session, step)
    return _prompt_for_step(step), step, True


def _set_outbound_step(session: Session, step: Optional[dict]) -> None:
    if step and step.get("type") == "mcq":
        step = _pad_edit_mcq_for_whatsapp(step)
        step = qb.enrich_mcq_step_for_whatsapp(step)
    if step:
        session.flow_state["edit_outbound_step"] = step
    else:
        session.flow_state.pop("edit_outbound_step", None)


def enter_edit_mode(session: Session) -> tuple[str, Optional[dict]]:
    se.reconcile_session(session)
    session.flow_state["edit_mode"] = True
    session.flow_state["edit_phase"] = "section"
    session.flow_state.pop("edit_section", None)
    session.flow_state.pop("edit_field", None)
    session.conversation_stage = ConversationStage.CONFIRMATION
    session.flow_state["current_stage"] = "final_review"
    session.flow_state["final_review_shown"] = True
    step = _section_menu_step()
    _set_outbound_step(session, step)
    step = get_outbound_step(session) or step
    return _prompt_for_step(step), step


def clear_edit_mode(session: Session) -> None:
    session.flow_state.pop("edit_mode", None)
    session.flow_state.pop("edit_phase", None)
    session.flow_state.pop("edit_section", None)
    session.flow_state.pop("edit_field", None)
    _set_outbound_step(session, None)


def _prompt_for_step(step: dict) -> str:
    if step.get("type") == "mcq":
        from backend.agents.chat.twilio_client import mcq_uses_interactive_delivery

        if mcq_uses_interactive_delivery(step):
            return str(step.get("prompt") or "").strip()
        return hybrid_flow.format_mcq_message(step)
    return str(step.get("prompt") or "")


def _section_menu_step() -> dict:
    return {
        "id": "edit_section_menu",
        "type": "mcq",
        "field": "__edit_section__",
        "prompt": "No problem 👍\n\nWhich section would you like to update?",
        "twilio_list_prompt": "Which section would you like to update?",
        "options": list(_SECTION_OPTIONS),
    }


def _field_menu_step(section: str, session: Session) -> dict:
    options = _fields_for_section(section, session)
    prompt = _FIELD_MENU_PROMPTS.get(
        section,
        "Which item would you like to update?",
    )
    return {
        "id": f"edit_field_menu_{section}",
        "type": "mcq",
        "field": "__edit_field__",
        "prompt": prompt,
        "options": options,
    }


def _file_action_step() -> dict:
    return {
        "id": "edit_file_action",
        "type": "mcq",
        "field": "__edit_file_action__",
        "prompt": "What would you like to do with your uploaded files?",
        "twilio_list_prompt": "What would you like to do with your uploaded files?",
        "options": list(_FILE_ACTION_OPTIONS) + [
            {"label": "Back to menu", "value": "back_to_sections", "whatsapp_label": "Back to menu"},
        ],
    }


def _post_edit_step() -> dict:
    return {
        "id": "edit_post_actions",
        "type": "mcq",
        "field": "__edit_post__",
        "prompt": "Does everything look correct?",
        "twilio_list_prompt": "Does everything look correct?",
        "options": list(_POST_EDIT_OPTIONS),
    }


def _fields_for_section(section: str, session: Session) -> list[dict]:
    if section == "client_details":
        steps = {s["field"]: s for s in qb.build_client_details_steps()}
        return [
            {"label": label, "value": field}
            for field, label in _CLIENT_FIELDS
            if field in steps
        ]
    if section == "service_selection":
        return [{"label": "Service", "value": "service_category"}]
    if section == "project_requirements":
        if not session.service_category:
            return []
        steps = qb.get_service_questionnaire_steps(session)
        return [
            {"label": _requirement_label(s), "value": s["field"]}
            for s in steps
            if s.get("type") == "mcq"
        ]
    if section == "additional_notes":
        steps = qb.get_service_questionnaire_steps(session)
        for s in steps:
            if s.get("type") == "descriptive":
                return [{"label": _requirement_label(s), "value": s["field"]}]
        return [{"label": "Additional Notes", "value": "service_q4"}]
    if section == "uploaded_files":
        return list(_FILE_ACTION_OPTIONS)
    return []


def _requirement_label(step: dict) -> str:
    prompt = str(step.get("prompt") or "").strip()
    if prompt:
        first = prompt.split("\n")[0].strip()
        if first.endswith("?"):
            return first
        return first.rstrip(".") + "?"
    field = step.get("field", "")
    return field.replace("_", " ").title()


def _resolve_section_choice(
    step: dict,
    user_message: str,
    *,
    button_text: str = "",
    button_payload: str = "",
    list_id: str = "",
) -> Optional[dict]:
    chosen = _resolve_mcq(
        step, user_message,
        button_text=button_text, button_payload=button_payload, list_id=list_id,
    )
    if chosen:
        return chosen
    alias = _SECTION_ALIASES.get((user_message or "").strip().lower())
    if alias:
        for opt in step.get("options", []):
            if opt.get("value") == alias:
                return opt
    return None


def _human_field_label(field: str, session: Session) -> str:
    for f, label in _CLIENT_FIELDS:
        if f == field:
            return label
    if field == "service_category":
        return "Service"
    if field == "service_q4":
        return "Additional notes"
    qstep = _step_for_field(session, field)
    if qstep:
        return _requirement_label(qstep).rstrip("?")
    return field.replace("_", " ").title()


def _edit_value_prompt(session: Session, field: str, qstep: dict) -> str:
    """Re-ask prompt with current value shown for text fields."""
    from backend.intelligence.display_labels import display_label

    label = _human_field_label(field, session)
    service_key = session.service_category.value if session.service_category else ""
    current = session.extracted_fields.get(field)
    current_display = ""
    if current and str(current).strip().lower() not in _SKIP_WORDS:
        current_display = display_label(field, current, service_category=service_key)

    if qstep.get("type") == "descriptive":
        question = str(qstep.get("prompt") or "Please type your updated answer.").strip()
        parts = [f"Got it — let's update your *{label}*."]
        if current_display:
            parts.extend(["", f"*Current answer:*\n{current_display}", ""])
        parts.append(question)
        if qstep.get("optional"):
            parts.append("\n(Reply *skip* to leave this blank.)")
        return "\n".join(parts)

    if field == "service_category":
        from backend.intelligence.consultants.registry import get_service_label

        current_svc = ""
        if session.service_category:
            current_svc = get_service_label(session.service_category)
        parts = ["Updating your *service selection*."]
        if current_svc:
            parts.extend(["", f"*Current service:* {current_svc}", ""])
        parts.append(edit_service_selection_step()["prompt"])
        parts.append("")
        for opt in edit_service_selection_step().get("options", []):
            parts.append(f"• {opt['label']}")
        parts.append("\n(Reply with the service name or number from the list.)")
        return "\n".join(parts)

    if qstep.get("type") == "mcq" and current_display:
        return (
            f"Updating *{label}*.\n\n"
            f"Current answer: {current_display}\n\n"
            + hybrid_flow.format_step_message(qstep, include_stage=False)
        )
    return hybrid_flow.format_step_message(qstep, include_stage=False)


def _start_field_edit(session: Session, field: str) -> tuple[str, Optional[dict], bool]:
    """Jump straight to re-asking a single field (skips redundant field menus)."""
    session.flow_state["edit_field"] = field
    session.flow_state["edit_phase"] = "value"
    qstep = _step_for_field(session, field)
    if not qstep:
        session.flow_state["edit_phase"] = "field"
        return "That field is not available for editing right now.", None, True
    _set_outbound_step(session, qstep if qstep.get("type") == "mcq" else None)
    return _edit_value_prompt(session, field, qstep), qstep if qstep.get("type") == "mcq" else None, True


def _step_for_field(session: Session, field: str) -> Optional[dict]:
    if field == "service_category":
        return edit_service_selection_step()
    if field in {f for f, _ in _CLIENT_FIELDS}:
        for s in qb.build_client_details_steps():
            if s.get("field") == field:
                return s
    if session.service_category:
        for s in qb.get_service_questionnaire_steps(session):
            if s.get("field") == field:
                return s
    return None


def _resolve_mcq(step: dict, user_message: str, *, button_text: str = "", button_payload: str = "", list_id: str = "") -> Optional[dict]:
    options = step.get("options", [])
    if list_id:
        for opt in options:
            if str(opt.get("value")) == list_id or str(opt.get("label")) == list_id:
                return opt
    tap = (button_text or button_payload or "").strip()
    if tap:
        matched = match_mcq_option(tap, options)
        if matched:
            return matched
    matched = match_mcq_option((user_message or "").strip(), options)
    return matched


def process_edit_turn(
    session: Session,
    user_message: str,
    *,
    button_text: str = "",
    button_payload: str = "",
    list_id: str = "",
) -> tuple[str, Optional[dict], bool]:
    """
    Returns (reply_text, outbound_step, handled).
    handled=False means caller should process normally (e.g. confirm submit).
    """
    if not is_active(session):
        return "", None, False

    phase = session.flow_state.get("edit_phase", "section")
    text = (user_message or "").strip()
    lower = text.lower()

    if phase == "post_edit":
        step = _post_edit_step()
        chosen = _resolve_mcq(step, text, button_text=button_text, button_payload=button_payload, list_id=list_id)
        if chosen:
            if chosen["value"] == "edit_again":
                msg, step = enter_edit_mode(session)
                return msg, step, True
            if chosen["value"] == "confirm_submit":
                clear_edit_mode(session)
                return "", None, False
        return (hybrid_flow.invalid_choice_reply(step), step, True)

    if phase == "section":
        step = _section_menu_step()
        chosen = _resolve_section_choice(
            step, text,
            button_text=button_text, button_payload=button_payload, list_id=list_id,
        )
        if not chosen:
            _set_outbound_step(session, step)
            return hybrid_flow.invalid_choice_reply(step), step, True
        section = chosen["value"]
        session.flow_state["edit_section"] = section
        if section == "uploaded_files":
            session.flow_state["edit_phase"] = "file_action"
            fstep = _file_action_step()
            _set_outbound_step(session, fstep)
            return _prompt_for_step(fstep), fstep, True
        fields = _fields_for_section(section, session)
        if not fields:
            return "No editable fields are available for this section right now.", None, True
        if len(fields) == 1:
            return _start_field_edit(session, str(fields[0]["value"]))
        session.flow_state["edit_phase"] = "field"
        fstep = _field_menu_step(section, session)
        _set_outbound_step(session, fstep)
        return _prompt_for_step(fstep), fstep, True

    if phase == "file_action":
        step = _file_action_step()
        chosen = _resolve_mcq(step, text, button_text=button_text, button_payload=button_payload, list_id=list_id)
        if not chosen:
            _set_outbound_step(session, step)
            return hybrid_flow.invalid_choice_reply(step), step, True
        action = chosen["value"]
        if action == "back_to_sections":
            return _return_to_section_menu(session)
        if action == "remove_existing_file":
            session.attachments = []
            se.mark_field_validated(session, "attachments", "skipped")
            return _finish_edit(session)
        if action in ("add_new_file", "replace_existing_file"):
            if action == "replace_existing_file":
                session.attachments = []
            session.flow_state["edit_phase"] = "awaiting_upload"
            _set_outbound_step(session, None)
            return "Please upload your file now (PDF, JPG, PNG, DWG). Reply *skip* if not applicable.", None, True
        return _prompt_for_step(step), step, True

    if phase == "field":
        section = session.flow_state.get("edit_section", "")
        step = _field_menu_step(section, session)
        chosen = _resolve_mcq(step, text, button_text=button_text, button_payload=button_payload, list_id=list_id)
        if not chosen:
            _set_outbound_step(session, step)
            return hybrid_flow.invalid_choice_reply(step), step, True
        if chosen["value"] == "back_to_sections":
            return _return_to_section_menu(session)
        field = chosen["value"]
        return _start_field_edit(session, field)

    if phase == "value":
        field = session.flow_state.get("edit_field", "")
        qstep = _step_for_field(session, field)
        if not qstep:
            clear_edit_mode(session)
            return "Edit session expired. Reply *Edit Details* to try again.", None, True

        if field == "service_category":
            edit_step = edit_service_selection_step()
            chosen = _resolve_mcq(
                edit_step, text,
                button_text=button_text, button_payload=button_payload, list_id=list_id,
            )
            category = None
            if chosen:
                try:
                    category = ServiceCategory(chosen["value"])
                except ValueError:
                    category = detect_service(chosen["value"])
            if category is None:
                category = detect_service(text or button_payload or list_id or button_text)
            if not category:
                _set_outbound_step(session, edit_step)
                return hybrid_flow.invalid_choice_reply(edit_step), edit_step, True
            session.service_category = category
            session.active_consultant = CONSULTANT_IDS[category]
            se.mark_field_validated(session, "service_category", category.value)
            se.mark_field_validated(session, "assigned_consultant", session.active_consultant or "")
            session.flow_state["selected_service"] = category.value
            session.flow_state["assigned_consultant"] = session.active_consultant or ""
            return _finish_edit(session)

        stype = qstep.get("type")
        if stype == "mcq":
            chosen = _resolve_mcq(
                qstep, text,
                button_text=button_text, button_payload=button_payload, list_id=list_id,
            )
            if not chosen:
                _set_outbound_step(session, qstep)
                return hybrid_flow.invalid_choice_reply(qstep), qstep, True
            value = chosen.get("value", chosen.get("label"))
        elif stype == "descriptive":
            if qstep.get("optional") and lower in _SKIP_WORDS:
                value = ""
            elif not text or lower in _SKIP_WORDS:
                prompt = _edit_value_prompt(session, field, qstep)
                return prompt, None, True
            else:
                value = text
        else:
            return "Unsupported field type for edit.", None, True

        if not se.mark_field_validated(session, field, value):
            prompt = _edit_value_prompt(session, field, qstep)
            return prompt + "\n\nPlease provide a valid answer.", qstep if stype == "mcq" else None, True

        session.flow_state.setdefault("answers", {})[field] = value
        return _finish_edit(session)

    if phase == "awaiting_upload":
        if lower in _SKIP_WORDS:
            return skip_file_upload(session)
        return "Please upload a file, or reply *skip* to continue without a file.", None, True

    clear_edit_mode(session)
    return "", None, False


def complete_file_upload(session: Session) -> tuple[str, Optional[dict], bool]:
    """Called after WhatsApp media is saved during edit upload phase."""
    count = len(session.attachments)
    value = f"{count} file(s) uploaded" if count else "skipped"
    se.mark_field_validated(session, "attachments", value)
    return _finish_edit(session)


def skip_file_upload(session: Session) -> tuple[str, Optional[dict], bool]:
    se.mark_field_validated(session, "attachments", "skipped")
    return _finish_edit(session)


def _finish_edit(session: Session) -> tuple[str, Optional[dict], bool]:
    se.reconcile_session(session)
    review = qb.format_final_review(session, include_footer=False)
    msg = f"Updated successfully ✅\n\n{review}"
    post_step = _post_edit_step()
    session.flow_state["edit_mode"] = True
    session.flow_state["edit_phase"] = "post_edit"
    session.flow_state.pop("edit_section", None)
    session.flow_state.pop("edit_field", None)
    _set_outbound_step(session, post_step)
    return msg, post_step, True


def wants_confirm_submit(
    message: str,
    *,
    list_id: str = "",
    button_payload: str = "",
    button_text: str = "",
) -> bool:
    tap = (list_id or button_payload or button_text or "").strip().lower()
    if tap in ("confirm_submit", "confirm & submit", "confirm and submit"):
        return True
    lower = (message or "").strip().lower()
    confirm_phrases = (
        "yes", "yep", "yeah", "correct", "confirm", "ok", "okay", "proceed", "sure",
        "confirm & submit", "confirm and submit", "submit",
    )
    return any(lower == p or lower.startswith(p + " ") for p in confirm_phrases)


def wants_edit_again(
    message: str,
    *,
    list_id: str = "",
    button_payload: str = "",
    button_text: str = "",
) -> bool:
    tap = (list_id or button_payload or button_text or "").strip().lower()
    if tap in ("edit_details", "edit details", "edit_again", "edit again"):
        return True
    lower = (message or "").strip().lower()
    return lower in ("edit", "edit details", "edit again", "change", "fix")

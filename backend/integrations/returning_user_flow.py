"""
Existing Tatva user flow after check-phone (case 2).
"""
from __future__ import annotations

from typing import Any, Optional

from backend.intelligence import hybrid_flow
from backend.intelligence import stage_engine as se
from backend.integrations.tatva_users import update_tatva_user_profile_for_session
from backend.schemas.session import Session

RETURNING_EDIT_DECISION_FIELD = "__returning_edit_info__"


def parse_yes_no_choice(
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


def returning_edit_decision_step() -> dict[str, Any]:
    return {
        "id": "returning_edit_decision",
        "type": "mcq",
        "field": RETURNING_EDIT_DECISION_FIELD,
        "prompt": "Do you want to edit your details?",
        "twilio_list_prompt": "Do you want to edit your details?",
        "options": [
            {"label": "Yes", "value": "yes"},
            {"label": "No", "value": "no"},
        ],
    }


def existing_user_welcome_text(session: Session) -> str:
    full_name = str(session.extracted_fields.get("client_name") or "").strip()
    hey = f"Hey {full_name}" if full_name else "Hey there"
    return (
        f"{hey} 👋\n\n"
        "I'm EVA, your TatvaOps assistant.\n\n"
        "TatvaOps helps homeowners build, renovate, and upgrade their homes with trusted experts, "
        "transparent workflows, and real-time project support.\n\n"
        "I'll guide you step-by-step and connect you with the right specialist for your project ✨"
    )


def _mark_profile_fields_complete(session: Session) -> None:
    phone = (session.extracted_fields.get("phone_number") or session.phone_number or "").strip()
    if phone.lower().startswith("whatsapp:"):
        phone = phone.split(":", 1)[-1]
    if phone:
        se.mark_field_validated(session, "phone_number", phone)

    name = str(session.extracted_fields.get("client_name") or "").strip()
    if name and not se.field_is_complete(session, "client_name"):
        se.mark_field_validated(session, "client_name", name)

    email = str(session.extracted_fields.get("email") or "").strip()
    if email and not se.field_is_complete(session, "email"):
        session.mark_field_complete("email", email)
    elif not se.field_is_complete(session, "email"):
        session.mark_field_complete("email", "")


def continue_existing_user_from_city(session: Session) -> str:
    """Skip name/email and continue client details from city."""
    se.start_client_stage(session)
    _mark_profile_fields_complete(session)
    session.flow_state["existing_user_skip_edit"] = True
    session.flow_state.pop("current_step_id", None)
    se.reconcile_session(session)
    step = hybrid_flow.get_current_step(session)
    if step:
        return hybrid_flow.format_step_message(step, include_stage=False)
    return "Which city are you located in?"


def start_existing_user_edit_name(session: Session) -> str:
    session.flow_state["awaiting_returning_edit_name"] = True
    session.flow_state.pop("awaiting_returning_edit_decision", None)
    return "Please type your full name."


def start_existing_user_edit_email(session: Session) -> str:
    session.flow_state["awaiting_returning_edit_email"] = True
    session.flow_state.pop("awaiting_returning_edit_name", None)
    return "Please type your email address (or reply *skip* to continue without email)."


async def complete_existing_user_edit_email(session: Session, text: str) -> tuple[Optional[str], str]:
    """Validate email, update Tatva profile, then continue from city."""
    raw = (text or "").strip()
    if raw.lower() in {"skip", "none", "later"}:
        session.mark_field_complete("email", "")
    elif raw:
        if "@" not in raw or "." not in raw.split("@")[-1]:
            return None, "Please enter a valid email address, or reply *skip*."
        session.mark_field_complete("email", raw)
    else:
        return None, "Please type your email address, or reply *skip*."

    session.flow_state.pop("awaiting_returning_edit_email", None)
    vendor_msg = await update_tatva_user_profile_for_session(session)
    if vendor_msg:
        return vendor_msg, vendor_msg
    return None, continue_existing_user_from_city(session)


def complete_existing_user_edit_name(session: Session, text: str) -> tuple[Optional[str], str]:
    name = (text or "").strip()
    if not name:
        return None, "Please type your full name."
    se.mark_field_validated(session, "client_name", name)
    return None, start_existing_user_edit_email(session)

"""
Existing Tatva user flow after check-phone (case 2).
"""
from __future__ import annotations

from typing import Any, Optional

from backend.intelligence import hybrid_flow
from backend.intelligence import stage_engine as se
from backend.intelligence import edit_flow
from backend.integrations.tatva_users import update_tatva_user_profile_for_session
from backend.schemas.session import ConversationStage, Session

RETURNING_EDIT_DECISION_FIELD = "__returning_edit_info__"
RETURNING_MISSING_LOCATION_PLACEHOLDER = "Not specified"

WILLING_TO_CREATE_PROJECT_FALLBACK = (
    "Would you like to proceed with creating your project? "
    "Once created, a dedicated Relationship Manager will guide you through every step.\n\n"
    "• Yes, Create My Project\n"
    "• No, I'm Just Exploring"
)


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
    greeting = f"Hi there {full_name} 👋" if full_name else "Hi there 👋"
    return (
        f"{greeting}\n\n"
        "Great to see you again! I'm EVA, your TatvaOps assistant.\n\n"
        "TatvaOps helps homeowners build, renovate, and upgrade their homes with trusted experts, "
        "transparent workflows, and real-time project support.\n\n"
        "I'll guide you step-by-step and connect you with the right specialist for your project ✨"
    )


def collect_returning_user_preserved_profile(session: Session) -> dict[str, str]:
    phone = (session.extracted_fields.get("phone_number") or session.phone_number or "").strip()
    if phone.lower().startswith("whatsapp:"):
        phone = phone.split(":", 1)[-1]
    return {
        "phone": phone,
        "tatva_user_id": str(session.extracted_fields.get("tatva_user_id") or "").strip(),
        "client_name": str(session.extracted_fields.get("client_name") or "").strip(),
        "email": str(session.extracted_fields.get("email") or "").strip(),
        "city": str(session.extracted_fields.get("city") or "").strip(),
        "property_location": str(session.extracted_fields.get("property_location") or "").strip(),
        "preferred_contact_time": str(session.extracted_fields.get("preferred_contact_time") or "").strip(),
    }


def complete_known_client_details_for_returning_user(
    session: Session,
    preserved: dict[str, str],
) -> None:
    """Mark profile fields complete so the next step is willing_to_create_project."""
    se.mark_field_validated(session, "ava_intro_shown", True)
    phone = preserved.get("phone", "")
    if phone:
        se.mark_field_validated(session, "phone_number", phone)

    name = preserved.get("client_name", "")
    if name:
        se.mark_field_validated(session, "client_name", name)

    email = preserved.get("email", "")
    if email and se.is_valid_gmail_address(email):
        se.mark_field_validated(session, "email", email)
    else:
        se.mark_field_validated(session, "email", "")

    city = preserved.get("city", "")
    prop = preserved.get("property_location", "")
    if not city and prop:
        city = prop.split(",")[0].strip()
    if not city:
        city = RETURNING_MISSING_LOCATION_PLACEHOLDER
    se.mark_field_validated(session, "city", city)

    if not prop:
        prop = RETURNING_MISSING_LOCATION_PLACEHOLDER
    se.mark_field_validated(session, "property_location", prop)

    contact = preserved.get("preferred_contact_time", "")
    if not contact:
        contact = "morning"
    se.mark_field_validated(session, "preferred_contact_time", contact)


def prepare_returning_user_for_project_decision(session: Session) -> str:
    """Clear the prior enquiry and position a returning user at willing_to_create_project."""
    preserved = collect_returning_user_preserved_profile(session)
    se.clear_prior_enquiry_qualification(session)
    edit_flow.clear_edit_mode(session)
    session.conversation_stage = ConversationStage.DETAIL_COLLECTION
    for key in (
        "conversation_ended",
        "final_review_shown",
        "final_review_outbound_step",
        "tatva_enquiry_submitted",
        "tatva_enquiry_summary",
        "tatva_enquiry_attachments",
        "tatva_enquiry_id",
    ):
        session.flow_state.pop(key, None)
    hybrid_flow.init_flow(session)
    complete_known_client_details_for_returning_user(session, preserved)
    if preserved["tatva_user_id"]:
        session.extracted_fields["tatva_user_id"] = preserved["tatva_user_id"]
        if "tatva_user_id" not in session.completed_fields:
            session.completed_fields.append("tatva_user_id")
    session.flow_state["returning_edit_flow_complete"] = True
    session.flow_state.pop("current_step_id", None)
    se.reconcile_session(session)
    step = hybrid_flow.get_current_step(session)
    if step and step.get("field") == "willing_to_create_project":
        return hybrid_flow.format_step_message(step, include_stage=False)
    return WILLING_TO_CREATE_PROJECT_FALLBACK


def continue_existing_user_from_city(session: Session) -> str:
    """After edit decision (or profile update), skip to project creation — not city/location."""
    return prepare_returning_user_for_project_decision(session)


def start_existing_user_edit_name(session: Session) -> str:
    session.flow_state["awaiting_returning_edit_name"] = True
    session.flow_state.pop("awaiting_returning_edit_decision", None)
    return "Please type your full name."


def start_existing_user_edit_email(session: Session) -> str:
    session.flow_state["awaiting_returning_edit_email"] = True
    session.flow_state.pop("awaiting_returning_edit_name", None)
    return "Please type your email address (or reply *skip* to continue without email)."


async def complete_existing_user_edit_email(session: Session, text: str) -> tuple[Optional[str], str]:
    """Validate email, update Tatva profile, then continue to project creation."""
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
    return None, prepare_returning_user_for_project_decision(session)


def complete_existing_user_edit_name(session: Session, text: str) -> tuple[Optional[str], str]:
    name = (text or "").strip()
    if not name:
        return None, "Please type your full name."
    se.mark_field_validated(session, "client_name", name)
    return None, start_existing_user_edit_email(session)

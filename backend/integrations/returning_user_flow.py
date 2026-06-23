"""
Existing Tatva user flow after check-phone (case 2).
"""
from __future__ import annotations

from typing import Any, Optional

from backend.intelligence import hybrid_flow
from backend.intelligence import stage_engine as se
from backend.intelligence import edit_flow
from backend.integrations.tatva_users import update_tatva_user_profile_for_session
from backend.integrations.tatva_user_addresses import (
    NO_RESPONSE_FROM_API,
    apply_tatva_address_to_session,
    get_cached_user_addresses,
    is_tatva_address_id,
    saved_addresses_display,
)
from backend.schemas.session import ConversationStage, Session

RETURNING_EDIT_DECISION_FIELD = "__returning_edit_info__"
RETURNING_LOCATION_FIELD = "__returning_location__"
RETURNING_MISSING_LOCATION_PLACEHOLDER = "Not specified"
RETURNING_MISSING_NAME_PLACEHOLDER = "__returning_user__"
_LEGACY_NAME_PLACEHOLDERS = frozenset({
    RETURNING_MISSING_NAME_PLACEHOLDER,
    "Registered User",
})


def is_placeholder_client_name(name: Any) -> bool:
    return str(name or "").strip() in _LEGACY_NAME_PLACEHOLDERS


def resolve_returning_client_name(
    session: Session,
    preserved: dict[str, str] | None = None,
) -> str:
    """Real Tatva/client name only — never the internal stage-completion placeholder."""
    for raw in (
        (preserved or {}).get("client_name", ""),
        str(session.extracted_fields.get("client_name") or "").strip(),
    ):
        candidate = str(raw or "").strip()
        if candidate and not is_placeholder_client_name(candidate):
            return candidate
    return ""


def display_client_name(session: Session) -> str:
    return resolve_returning_client_name(session)


def clear_placeholder_client_name(session: Session) -> None:
    if is_placeholder_client_name(session.extracted_fields.get("client_name")):
        session.extracted_fields.pop("client_name", None)
        session.completed_fields = [f for f in session.completed_fields if f != "client_name"]


def is_returning_registered_user(session: Session) -> bool:
    """True when this chat is the Tatva returning-user path (not a fresh signup)."""
    fs = session.flow_state or {}
    return bool(
        fs.get("returning_edit_flow_complete")
        or fs.get("existing_user_flow_started")
        or fs.get("tatva_user_registered")
    )

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


def saved_location_display(session: Session) -> str:
    """Format saved locations from Tatva address API only."""
    api_display = saved_addresses_display(session)
    if api_display:
        return api_display
    return NO_RESPONSE_FROM_API


def address_short_list_label(index: int) -> str:
    """Short WhatsApp list row label — full address is sent in the preceding text message."""
    return f"Address {index}"


def _resolve_address_index_choice(selected: str, session: Session) -> Optional[str]:
    """Map 'Address N', 'address n', or plain 'N' to a Tatva address _id."""
    needle = (selected or "").strip()
    if not needle:
        return None
    addresses = get_cached_user_addresses(session)
    if not addresses:
        return None

    lowered = needle.lower()
    index: Optional[int] = None
    if lowered.startswith("address"):
        suffix = lowered.removeprefix("address").strip()
        if suffix.isdigit():
            index = int(suffix)
    elif needle.isdigit():
        index = int(needle)

    if index is None or index < 1 or index > len(addresses):
        return None
    addr_id = str(addresses[index - 1].get("_id") or "").strip()
    return addr_id or None


def has_returning_saved_addresses(session: Session) -> bool:
    return bool(get_cached_user_addresses(session))


def returning_saved_location_context(session: Session) -> str:
    display = saved_location_display(session)
    addresses = get_cached_user_addresses(session)
    if addresses:
        return f"Here are your saved locations:\n\n{display}"
    return display


def returning_saved_location_step(session: Session) -> dict[str, Any] | None:
    context = returning_saved_location_context(session)
    addresses = get_cached_user_addresses(session)
    if not addresses:
        return None
    options: list[dict[str, str]] = []
    for i, addr in enumerate(addresses[:5], start=1):
        options.append({
            "label": address_short_list_label(i),
            "value": str(addr.get("_id") or ""),
        })
    options.append({"label": "Other address", "value": "add_new_location"})
    return {
        "id": "returning_location_confirm",
        "type": "mcq",
        "field": RETURNING_LOCATION_FIELD,
        "prompt": context,
        "twilio_list_prompt": "Choose your saved location",
        "options": options,
    }


def _parse_single_location_choice(
    selected: str,
    *,
    session: Session | None = None,
) -> Optional[str]:
    needle = (selected or "").strip()
    if not needle:
        return None
    selected_l = needle.lower()
    if session and is_tatva_address_id(needle, session):
        return needle
    if session:
        by_index = _resolve_address_index_choice(needle, session)
        if by_index:
            return by_index
    if selected_l in {"confirm_saved", "yes", "y", "correct", "this is correct"}:
        return "confirm_saved"
    if selected_l in {
        "add_new_location",
        "add new location",
        "other address",
        "other",
        "new location",
        "new",
        "add",
    }:
        return "add_new_location"
    if "correct" in selected_l or selected_l.startswith("yes"):
        return "confirm_saved"
    if "new" in selected_l and "location" in selected_l:
        return "add_new_location"
    return None


def parse_returning_location_choice(
    user_message: str,
    *,
    list_id: str = "",
    button_payload: str = "",
    button_text: str = "",
    session: Session | None = None,
) -> Optional[str]:
    candidates: list[str] = []
    for raw in (list_id, button_payload, button_text, user_message):
        selected = (raw or "").strip()
        if not selected:
            continue
        candidates.append(selected)
        for line in selected.replace("\r", "\n").split("\n"):
            line = line.strip()
            if line:
                candidates.append(line)

    seen: set[str] = set()
    for selected in candidates:
        key = selected.lower()
        if key in seen:
            continue
        seen.add(key)
        choice = _parse_single_location_choice(selected, session=session)
        if choice:
            return choice
    return None


def apply_returning_location_choice(session: Session, choice: str) -> None:
    """Persist the user's location selection on the session."""
    if choice == "add_new_location":
        session.flow_state["returning_wants_new_location"] = True
        return
    if choice == "confirm_saved":
        return
    apply_tatva_address_to_session(session, choice)


def existing_user_welcome_text(session: Session) -> str:
    full_name = display_client_name(session)
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
        "client_name": resolve_returning_client_name(session),
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

    name = resolve_returning_client_name(session, preserved)
    if name:
        se.mark_field_validated(session, "client_name", name)
    elif not se.field_is_complete(session, "client_name"):
        # Internal sentinel so returning users are not re-asked for their name.
        se.mark_field_validated(session, "client_name", RETURNING_MISSING_NAME_PLACEHOLDER)

    email = preserved.get("email", "")
    if email and se.is_valid_email_address(email):
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


def advance_returning_user_to_service_selection(session: Session) -> None:
    """Skip client-detail prompts for registered users and open service selection."""
    clear_placeholder_client_name(session)
    preserved = collect_returning_user_preserved_profile(session)
    complete_known_client_details_for_returning_user(session, preserved)
    se.mark_field_validated(session, "willing_to_create_project", "yes")
    se.mark_stage_complete(session, "ava_intro")
    se.mark_stage_complete(session, "client_details")
    session.flow_state["current_stage"] = "service_selection"
    session.flow_state.pop("current_step_id", None)
    session.flow_state.pop("last_stage_shown", None)
    se.set_current_question(session, None)
    se.reconcile_session(session)


def willing_to_create_project_step() -> dict[str, Any] | None:
    from backend.intelligence.qualification_builder import build_client_details_steps

    for step in build_client_details_steps():
        if step.get("field") == "willing_to_create_project":
            return dict(step)
    return None


def position_session_for_project_decision(session: Session) -> dict[str, Any] | None:
    """Prepare returning user and return the project-creation MCQ step."""
    prepare_returning_user_for_project_decision(session)
    step = willing_to_create_project_step()
    if not step:
        return None
    session.flow_state["current_step_id"] = step["id"]
    session.flow_state["current_stage"] = "client_details"
    se.set_current_question(session, "willing_to_create_project")
    return step


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
    step = willing_to_create_project_step()
    if step:
        return str(step.get("twilio_list_prompt") or step.get("prompt") or "").strip()
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
        if not se.is_valid_email_address(raw):
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

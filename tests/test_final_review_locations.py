"""Quick review location field labels."""
from datetime import datetime

from backend.schemas.session import Session, ConversationStage, AttachmentMeta
from backend.schemas.service import ServiceCategory
from backend.intelligence import stage_engine as se
from backend.intelligence import hybrid_flow
from backend.intelligence.qualification_builder import format_final_review


def test_final_review_shows_location_and_property_location_separately():
    session = Session(
        session_id="t",
        phone_number="whatsapp:+91999",
        channel="whatsapp",
        conversation_stage=ConversationStage.CONFIRMATION,
        service_category=ServiceCategory.PROPERTY_DEVELOPMENT,
        active_consultant="vikram",
    )
    se.mark_field_validated(session, "ava_intro_shown", True)
    for field, value in (
        ("client_name", "Navya"),
        ("phone_number", "+919999999999"),
        ("city", "Hyderabad"),
        ("property_location", "Bengaluru, hsr layout"),
        ("preferred_contact_time", "evening"),
        ("willing_to_create_project", "yes"),
        ("email", "skipped"),
    ):
        se.mark_field_validated(session, field, value)
    se.on_service_selected(session, ServiceCategory.PROPERTY_DEVELOPMENT)
    for field, value in (
        ("service_q1", "residential_plots_layouts"),
        ("service_q2", "land_feasibility_study"),
        ("service_q3", "1_5_cr"),
        ("service_q4", "notes"),
        ("attachments", "skipped"),
    ):
        se.mark_field_validated(session, field, value)
    se.enter_final_review(session)

    recap = format_final_review(session)

    assert "- Location: Hyderabad" in recap
    assert "- Property location: Bengaluru, hsr layout" in recap
    assert recap.index("Location:") < recap.index("Property location:")


def test_requirements_shared_lists_answers_only():
    session = Session(
        session_id="t",
        phone_number="whatsapp:+91999",
        channel="whatsapp",
        conversation_stage=ConversationStage.CONFIRMATION,
        service_category=ServiceCategory.EVENT_MANAGEMENT,
        active_consultant="meera",
    )
    se.mark_field_validated(session, "ava_intro_shown", True)
    for field, value in (
        ("client_name", "Navya"),
        ("phone_number", "+919999999999"),
        ("city", "Hyderabad"),
        ("property_location", "HSR"),
        ("preferred_contact_time", "evening"),
        ("willing_to_create_project", "yes"),
    ):
        se.mark_field_validated(session, field, value)
    se.on_service_selected(session, ServiceCategory.EVENT_MANAGEMENT)
    for field, value in (
        ("service_q1", "wedding"),
        ("service_q2", "50_150"),
        ("service_q3", "full_event_management"),
        ("service_q4", "16th June"),
        ("attachments", "skipped"),
    ):
        se.mark_field_validated(session, field, value)
    se.enter_final_review(session)

    recap = format_final_review(session)

    assert "*Requirements Shared*" in recap
    assert "What type of event are you planning - Wedding" in recap
    assert " - " in recap
    assert "?: " not in recap
    assert "planning?: " not in recap


def test_final_review_shows_actual_attachment_count():
    session = Session(
        session_id="t",
        phone_number="whatsapp:+91999",
        channel="whatsapp",
        conversation_stage=ConversationStage.CONFIRMATION,
        service_category=ServiceCategory.HOME_INTERIORS,
        active_consultant="aadhya",
    )
    se.mark_field_validated(session, "ava_intro_shown", True)
    for field, value in (
        ("client_name", "Navya"),
        ("phone_number", "+919999999999"),
        ("city", "Bengaluru"),
        ("property_location", "HSR Layout"),
        ("preferred_contact_time", "afternoon"),
        ("willing_to_create_project", "yes"),
        ("email", "skipped"),
    ):
        se.mark_field_validated(session, field, value)
    se.on_service_selected(session, ServiceCategory.HOME_INTERIORS)
    for field, value in (
        ("service_q1", "wardrobe_storage"),
        ("service_q2", "minimalist"),
        ("service_q3", "5_15L"),
        ("service_q4", "Noo Data"),
    ):
        se.mark_field_validated(session, field, value)
    se.mark_field_validated(session, "attachments", "1 file uploaded")
    for i in range(4):
        session.attachments.append(
            AttachmentMeta(
                file_name=f"photo_{i}.jpg",
                file_url=f"https://example.com/photo_{i}.jpg",
                mime_type="image/jpeg",
                uploaded_at=datetime.utcnow(),
            )
        )
    se.enter_final_review(session)

    recap = format_final_review(session)

    assert "- ↗ View image" in recap
    assert recap.count("↗ View image") == 4
    assert hybrid_flow.attachment_upload_value(session) == "4 files uploaded"


def test_final_review_preserves_exact_user_input_casing():
    session = Session(
        session_id="t",
        phone_number="whatsapp:+91999",
        channel="whatsapp",
        conversation_stage=ConversationStage.CONFIRMATION,
        service_category=ServiceCategory.HOME_INTERIORS,
        active_consultant="aadhya",
    )
    se.mark_field_validated(session, "ava_intro_shown", True)
    for field, value in (
        ("client_name", "VidyMN"),
        ("phone_number", "+918618387471"),
        ("city", "Mysore"),
        ("property_location", "Mysore, JP Nagar"),
        ("preferred_contact_time", "night"),
        ("willing_to_create_project", "yes"),
        ("email", "vidya@gmail.com"),
    ):
        se.mark_field_validated(session, field, value)
    se.on_service_selected(session, ServiceCategory.HOME_INTERIORS)
    for field, value in (
        ("service_q1", "wardrobe_storage"),
        ("service_q2", "minimalist"),
        ("service_q3", "5_15L"),
        ("service_q4", "Noo Data"),
        ("attachments", "skipped"),
    ):
        se.mark_field_validated(session, field, value)
    se.enter_final_review(session)

    recap = format_final_review(session)

    assert "- Name: VidyMN" in recap
    assert "- Location: Mysore" in recap
    assert "- Property location: Mysore, JP Nagar" in recap
    assert "- Email: vidya@gmail.com" in recap
    assert "Jp Nagar" not in recap
    assert "Vidya Mn" not in recap

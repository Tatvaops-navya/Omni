"""Stage validation and fuzzy input tests."""
from backend.schemas.service import ServiceCategory
from backend.schemas.session import Session, ConversationStage
from backend.intelligence import stage_engine as se
from backend.intelligence import hybrid_flow
from backend.intelligence.input_normalizer import match_mcq_option
from backend.intelligence.qualification_builder import build_client_details_steps


def test_fuzzy_morning_contact_time():
    step = next(s for s in build_client_details_steps() if s["field"] == "preferred_contact_time")
    options = step["options"]
    matched = match_mcq_option("morning hours", options)
    assert matched is not None
    assert matched["value"] == "morning"


def test_invalid_empty_field_not_complete():
    session = Session(session_id="t", phone_number="+1", conversation_stage=ConversationStage.ROUTING)
    se.mark_field_validated(session, "client_name", "")
    assert not se.field_is_complete(session, "client_name")


def test_cannot_enter_final_review_with_partial_data():
    session = Session(
        session_id="t", phone_number="+1",
        service_category=ServiceCategory.ELECTRICAL,
        conversation_stage=ConversationStage.DETAIL_COLLECTION,
    )
    se.mark_field_validated(session, "client_name", "Navya")
    se.mark_field_validated(session, "city", "Hyderabad")
    assert not se.can_enter_final_review(session)


def test_reconcile_resets_premature_final_review():
    session = Session(
        session_id="t", phone_number="+1",
        service_category=ServiceCategory.ELECTRICAL,
        conversation_stage=ConversationStage.CONFIRMATION,
        flow_state={"current_stage": "final_review", "completed_stages": ["client_details"]},
    )
    session.completed_fields = ["client_name", "phone_number"]
    se.reconcile_session(session)
    assert session.flow_state["current_stage"] != "final_review"
    assert session.conversation_stage != ConversationStage.CONFIRMATION or not se.can_enter_final_review(session)


def test_complete_attachment_upload_moves_to_review():
    session = Session(
        session_id="t", phone_number="+1",
        service_category=ServiceCategory.ELECTRICAL,
        conversation_stage=ConversationStage.DETAIL_COLLECTION,
    )
    for field in se.required_fields_for_summary(session):
        if field == "attachments":
            continue
        se.mark_field_validated(session, field, "test_value")
    se.mark_field_validated(session, "service_category", "electrical")
    session.service_category = ServiceCategory.ELECTRICAL
    session.flow_state["current_stage"] = "attachments"
    session.attachments.append(
        type("M", (), {"file_name": "plan.png", "file_url": "http://x", "mime_type": "image/png"})()
    )
    from backend.schemas.session import AttachmentMeta
    session.attachments = [
        AttachmentMeta(file_name="plan.png", file_url="http://x", mime_type="image/png")
    ]
    msg = hybrid_flow.complete_attachment_upload(session)
    assert se.fs_current_stage(session) == "final_review"
    assert session.flow_state.get("final_review_outbound_step")
    assert "quick review" in msg.lower()
    assert "Reply *Confirm & Submit*" not in msg


def test_stage_advances_one_at_a_time():
    session = Session(session_id="t", phone_number="+919999999999", conversation_stage=ConversationStage.ROUTING)
    se.start_client_stage(session)
    se.mark_field_validated(session, "client_name", "Test")
    before = se.fs_current_stage(session)
    se.maybe_advance_current_stage(session)
    after = se.fs_current_stage(session)
    assert before == "client_details"
    assert after == "client_details"


def test_valid_gmail_address_accepted():
    assert se.is_valid_gmail_address("vidya@gmail.com")
    assert se.is_valid_gmail_address("Vidya.Moolehatty@gmail.com")
    assert se.mark_field_validated(
        Session(session_id="t", phone_number="+1", conversation_stage=ConversationStage.ROUTING),
        "email",
        "vidya@gmail.com",
    )


def test_invalid_email_rejected():
    assert not se.is_valid_gmail_address("vidyajdnuhh")
    assert not se.is_valid_gmail_address("name@yahoo.com")
    assert not se.is_valid_gmail_address("@gmail.com")
    session = Session(session_id="t", phone_number="+1", conversation_stage=ConversationStage.ROUTING)
    assert not se.mark_field_validated(session, "email", "vidyajdnuhh")


def test_email_skip_still_allowed():
    session = Session(session_id="t", phone_number="+1", conversation_stage=ConversationStage.ROUTING)
    assert se.mark_field_validated(session, "email", "")
    assert session.extracted_fields.get("email") == ""


def test_random_text_at_email_step_does_not_advance():
    session = Session(
        session_id="t",
        phone_number="whatsapp:+919999999999",
        channel="whatsapp",
        conversation_stage=ConversationStage.ROUTING,
    )
    se.start_client_stage(session)
    for field, value in (
        ("client_name", "Vidya"),
        ("city", "Mysore"),
        ("property_location", "Mysore, Kuvempunagar"),
    ):
        se.mark_field_validated(session, field, value)
    se.reconcile_session(session)

    reply, handled = hybrid_flow.process_hybrid_turn(session, "vidyajdnuhh")
    assert handled is True
    assert reply is not None
    assert "valid Gmail address" in reply
    assert not se.field_is_complete(session, "email")


def test_gmail_at_email_step_is_accepted():
    session = Session(
        session_id="t",
        phone_number="whatsapp:+919999999999",
        channel="whatsapp",
        conversation_stage=ConversationStage.ROUTING,
    )
    se.start_client_stage(session)
    for field, value in (
        ("client_name", "Vidya"),
        ("city", "Mysore"),
        ("property_location", "Mysore, Kuvempunagar"),
    ):
        se.mark_field_validated(session, field, value)
    se.reconcile_session(session)

    reply, handled = hybrid_flow.process_hybrid_turn(session, "vidya@gmail.com")
    assert handled is True
    assert se.field_is_complete(session, "email")
    assert session.extracted_fields.get("email") == "vidya@gmail.com"

"""Omnichannel platform tests."""
import pytest

from backend.schemas.service import ServiceCategory
from backend.schemas.session import Session, ConversationStage, MessageRole
from backend.intelligence.nova_router import detect_service, SERVICE_MENU_PROMPT
from backend.intelligence import hybrid_flow
from backend.intelligence import stage_engine as se
from backend.intelligence.lead_scorer import score_lead
from backend.intelligence.conversation_controller import ConversationController, _is_off_topic
from backend.intelligence.persona import GUARDRAIL_REDIRECT
from backend.agents.chat.whatsapp_handler import (
    _is_new_enquiry_intent,
    _is_post_submit_polite_reply,
    _first_name,
    _more_file_upload_step,
    _parse_yes_no_choice,
    _returning_edit_decision_step,
    _returning_user_greeting_text,
    _is_in_returning_user_prompt,
    _debounced_file_upload_follow_up,
)
from backend.utils.session_idle import (
    is_session_idle_expired,
    idle_timeout_notice,
    should_prepend_idle_notice,
    is_greeting_message,
    build_idle_fresh_start_reply,
)
from datetime import datetime, timedelta


def test_session_idle_expired_after_five_minutes():
    session = Session(
        session_id="wa_test",
        phone_number="whatsapp:+91999",
        channel="whatsapp",
        conversation_stage=ConversationStage.DETAIL_COLLECTION,
        last_active=datetime.utcnow() - timedelta(minutes=6),
    )
    assert is_session_idle_expired(session) is True


def test_submitted_session_not_idle_expired():
    session = Session(
        session_id="wa_test",
        phone_number="whatsapp:+91999",
        channel="whatsapp",
        conversation_stage=ConversationStage.SUMMARY_GENERATED,
        summary_generated=True,
        last_active=datetime.utcnow() - timedelta(hours=2),
    )
    assert is_session_idle_expired(session) is False


def test_idle_timeout_notice_text():
    assert "5 minutes" in idle_timeout_notice()


def test_greeting_after_idle_does_not_show_timeout_banner():
    session = Session(
        session_id="wa_test",
        phone_number="whatsapp:+91999",
        channel="whatsapp",
        conversation_stage=ConversationStage.DETAIL_COLLECTION,
        flow_state={"current_stage": "client_details"},
        turn_count=2,
        last_active=datetime.utcnow() - timedelta(minutes=10),
    )
    assert is_greeting_message("hello") is True
    assert should_prepend_idle_notice(session, "hello") is False


def test_mid_flow_answer_after_idle_shows_timeout_banner():
    session = Session(
        session_id="wa_test",
        phone_number="whatsapp:+91999",
        channel="whatsapp",
        conversation_stage=ConversationStage.DETAIL_COLLECTION,
        flow_state={"current_stage": "client_details"},
        turn_count=2,
        last_active=datetime.utcnow() - timedelta(minutes=10),
    )
    assert should_prepend_idle_notice(session, "Rahul Sharma") is True


def test_idle_fresh_start_reply_includes_eva_intro_not_stale_answer():
    """Stale MCQ/list reply after timeout must restart at EVA intro + name question."""
    stale = Session(
        session_id="wa_test",
        phone_number="whatsapp:+91999",
        channel="whatsapp",
        conversation_stage=ConversationStage.DETAIL_COLLECTION,
        flow_state={"current_stage": "consultant_assignment"},
        turn_count=5,
        last_active=datetime.utcnow() - timedelta(minutes=10),
    )
    reply = build_idle_fresh_start_reply(stale, "Office / Commercial S...")
    assert "inactivity" in reply
    assert "I'm EVA" in reply
    assert "What is your full name?" in reply
    assert "Which city" not in reply


def test_idle_fresh_start_reply_greeting_skips_timeout_banner():
    stale = Session(
        session_id="wa_test",
        phone_number="whatsapp:+91999",
        channel="whatsapp",
        conversation_stage=ConversationStage.DETAIL_COLLECTION,
        flow_state={"current_stage": "client_details"},
        turn_count=2,
        last_active=datetime.utcnow() - timedelta(minutes=10),
    )
    reply = build_idle_fresh_start_reply(stale, "Hi")
    assert "inactivity" not in reply
    assert "I'm EVA" in reply
    assert "What is your full name?" in reply


def test_stale_intro_session_hello_no_timeout_banner():
    session = Session(
        session_id="wa_test",
        phone_number="whatsapp:+91999",
        channel="whatsapp",
        conversation_stage=ConversationStage.ROUTING,
        flow_state={"current_stage": "ava_intro"},
        last_active=datetime.utcnow() - timedelta(hours=1),
    )
    assert should_prepend_idle_notice(session, "hello") is False


def test_post_submit_message_intent():
    assert _is_post_submit_polite_reply("Thank you")
    assert not _is_new_enquiry_intent("Thank you")
    assert _is_new_enquiry_intent("Hello")
    assert _is_new_enquiry_intent("Hi there")


def test_more_file_upload_step_has_yes_no_options():
    step = _more_file_upload_step()
    assert step["field"] == "__more_file_upload__"
    assert step["type"] == "mcq"
    assert step["prompt"].lower().startswith("do you want to add")
    assert [o["value"] for o in step["options"]] == ["yes", "no"]


def test_parse_yes_no_choice_accepts_text_and_list_taps():
    assert _parse_yes_no_choice("yes") is True
    assert _parse_yes_no_choice("NO") is False
    assert _parse_yes_no_choice("", list_id="yes") is True
    assert _parse_yes_no_choice("", button_payload="no") is False
    assert _parse_yes_no_choice("maybe later") is None


def test_returning_user_steps_and_greeting():
    decision = _returning_edit_decision_step()
    assert decision["field"] == "__returning_edit_info__"
    assert [o["value"] for o in decision["options"]] == ["yes", "no"]

    session = Session(
        session_id="wa_test",
        phone_number="whatsapp:+91999",
        channel="whatsapp",
        conversation_stage=ConversationStage.SUMMARY_GENERATED,
        summary_generated=True,
    )
    session.extracted_fields["client_name"] = "John Doe"
    session.extracted_fields["email"] = "pramod.d@tatvaops.com"
    text = _returning_user_greeting_text(session)
    assert "Hey John Doe" in text
    assert "EVA" in text
    assert _first_name("Rahul Sharma") == "Rahul"


def test_returning_profile_field_uses_interactive_list(monkeypatch):
    from backend.agents.chat import twilio_client
    from backend.agents.chat.twilio_client import enrich_whatsapp_mcq_step, mcq_uses_interactive_delivery
    from backend.config import get_settings

    monkeypatch.setenv("TWILIO_MCQ_LIST_3_CONTENT_SID", "HX3row000000000000000000000000001")
    monkeypatch.setenv("TWILIO_WHATSAPP_QUICK_REPLY", "true")
    get_settings.cache_clear()
    monkeypatch.setattr(twilio_client, "settings", get_settings())

    step = enrich_whatsapp_mcq_step(_returning_profile_field_step())
    assert step["twilio_content_sid"] == "HX3row000000000000000000000000001"
    assert mcq_uses_interactive_delivery(step) is True


def test_returning_profile_selection_maps_no_to_continue():
    assert _returning_profile_selection(user_message="no") == "continue"
    assert _returning_profile_selection(list_id="client_name") == "client_name"
    assert _returning_profile_selection(user_message="name") == "client_name"
    assert _returning_profile_selection(user_message="continue") == "continue"


@pytest.mark.asyncio
async def test_returning_user_yes_to_edit_sends_list_template(monkeypatch):
    from backend.agents.chat import whatsapp_handler as wh

    session = Session(
        session_id="wa_test",
        phone_number="whatsapp:+91999",
        channel="whatsapp",
        conversation_stage=ConversationStage.SUMMARY_GENERATED,
        summary_generated=True,
    )
    session.flow_state["awaiting_returning_edit_decision"] = True

    sent: list[tuple[str, str]] = []

    async def fake_get_session(_session_id):
        return session

    async def fake_save_session(_session):
        return None

    async def fake_upsert_session_log(_session):
        return None

    async def fake_send_returning_mcq_prompt(_phone, context, _step):
        sent.append((context, str(_step.get("field"))))

    monkeypatch.setattr(wh, "get_session", fake_get_session)
    monkeypatch.setattr(wh, "save_session", fake_save_session)
    monkeypatch.setattr(wh.supabase_store, "upsert_session_log", fake_upsert_session_log)
    monkeypatch.setattr(wh, "_send_returning_mcq_prompt", fake_send_returning_mcq_prompt)

    await wh._handle_whatsapp_message_impl(
        "wa_test",
        "whatsapp:+91999",
        "yes",
        list_id="yes",
    )

    assert sent == [("", "__returning_profile_field__")]
    assert session.flow_state.get("awaiting_returning_profile_field") is True


@pytest.mark.asyncio
async def test_returning_user_no_after_name_update_continues(monkeypatch):
    from backend.agents.chat import whatsapp_handler as wh

    session = Session(
        session_id="wa_test",
        phone_number="whatsapp:+91999",
        channel="whatsapp",
        conversation_stage=ConversationStage.SUMMARY_GENERATED,
        summary_generated=True,
    )
    session.extracted_fields["tatva_user_id"] = "abc"
    session.flow_state["awaiting_returning_profile_field"] = True

    willing_calls: list[str] = []

    async def fake_get_session(_session_id):
        return session

    async def fake_save_session(_session):
        return None

    async def fake_upsert_session_log(_session):
        return None

    async def fake_send_willing(_s, phone):
        willing_calls.append(phone)

    monkeypatch.setattr(wh, "get_session", fake_get_session)
    monkeypatch.setattr(wh, "save_session", fake_save_session)
    monkeypatch.setattr(wh.supabase_store, "upsert_session_log", fake_upsert_session_log)
    monkeypatch.setattr(wh, "_send_willing_to_create_project_prompt", fake_send_willing)

    await wh._handle_whatsapp_message_impl(
        "wa_test",
        "whatsapp:+91999",
        "no",
    )

    assert willing_calls == ["whatsapp:+91999"]
    assert "awaiting_returning_profile_field" not in session.flow_state


def test_returning_user_prepare_clears_prior_enquiry_fields():
    from backend.agents.chat.whatsapp_handler import _prepare_returning_user_client_stage

    session = Session(
        session_id="wa_test",
        phone_number="whatsapp:+91999",
        channel="whatsapp",
        conversation_stage=ConversationStage.SUMMARY_GENERATED,
        summary_generated=True,
        service_category=ServiceCategory.ELECTRICAL,
    )
    session.extracted_fields.update({
        "client_name": "Shree",
        "email": "navya@gmail.com",
        "city": "Hyderabad",
        "property_location": "Madhapur",
        "preferred_contact_time": "morning",
        "willing_to_create_project": "yes",
        "service_category": "electrical",
        "service_q1": "new_wiring_rewiring",
        "service_q2": "residential_apartment",
        "tatva_user_id": "abc123",
    })
    session.completed_fields = [
        "client_name", "city", "property_location", "preferred_contact_time",
        "willing_to_create_project", "service_category", "service_q1", "service_q2",
        "tatva_user_id",
    ]
    session.flow_state["service_questionnaire_required_fields"] = [
        "service_q1", "service_q2", "service_q3", "service_q4", "attachments",
    ]

    _prepare_returning_user_client_stage(session)

    assert session.service_category is None
    assert "service_category" not in session.completed_fields
    assert "willing_to_create_project" not in session.completed_fields
    assert "service_q1" not in session.extracted_fields
    assert se.needs_client_details(session)
    assert not se.needs_service_selection(session)
    step = hybrid_flow.get_current_step(session)
    assert step is not None
    assert step.get("field") == "willing_to_create_project"


@pytest.mark.asyncio
async def test_returning_user_yes_then_service_selection_not_stale():
    from backend.agents.chat.whatsapp_handler import _prepare_returning_user_client_stage
    from backend.intelligence.conversation_controller import ConversationController

    session = Session(
        session_id="wa_test",
        phone_number="whatsapp:+91999",
        channel="whatsapp",
        conversation_stage=ConversationStage.SUMMARY_GENERATED,
        summary_generated=True,
        service_category=ServiceCategory.ELECTRICAL,
    )
    session.extracted_fields.update({
        "client_name": "Shree",
        "email": "navya@gmail.com",
        "city": "Hyderabad",
        "property_location": "Madhapur",
        "preferred_contact_time": "morning",
        "willing_to_create_project": "yes",
        "service_category": "electrical",
        "service_q1": "new_wiring_rewiring",
        "tatva_user_id": "abc123",
    })
    session.completed_fields = [
        "client_name", "city", "property_location", "preferred_contact_time",
        "willing_to_create_project", "service_category", "service_q1", "tatva_user_id",
    ]

    _prepare_returning_user_client_stage(session)
    controller = ConversationController()

    yes_resp = await controller.process_message(session, "yes", channel="whatsapp", list_id="yes")
    assert "didn't quite get that" not in (yes_resp.text or "").lower()
    assert se.needs_service_selection(session)

    stale = hybrid_flow.check_stale_interactive_selection(
        session,
        list_id="electrical",
    )
    assert stale is None

    svc_resp = await controller.process_message(
        session,
        "",
        channel="whatsapp",
        list_id="electrical",
        button_text="Electrical",
    )
    assert "already answered that question" not in (svc_resp.text or "").lower()
    assert session.service_category == ServiceCategory.ELECTRICAL


def test_touch_activity_prevents_false_idle_reset():
    session = Session(
        session_id="wa_test",
        phone_number="whatsapp:+91999",
        channel="whatsapp",
        conversation_stage=ConversationStage.ROUTING,
        summary_generated=False,
        last_active=datetime.utcnow() - timedelta(hours=2),
    )
    session.last_active = datetime.utcnow()
    assert not is_session_idle_expired(session)


def test_returning_user_prompt_blocks_duplicate_greeting_restart():
    session = Session(
        session_id="wa_test",
        phone_number="whatsapp:+91999",
        channel="whatsapp",
        conversation_stage=ConversationStage.SUMMARY_GENERATED,
        summary_generated=True,
    )
    assert not _is_in_returning_user_prompt(session)

    session.flow_state["awaiting_returning_edit_decision"] = True
    assert _is_in_returning_user_prompt(session)

    session.flow_state.pop("awaiting_returning_edit_decision")
    session.flow_state["awaiting_returning_profile_field"] = True
    assert _is_in_returning_user_prompt(session)


@pytest.mark.asyncio
async def test_second_greeting_while_awaiting_edit_reprompts_not_welcome_back(monkeypatch):
    from backend.agents.chat import whatsapp_handler as wh

    session = Session(
        session_id="wa_test",
        phone_number="whatsapp:+91999",
        channel="whatsapp",
        conversation_stage=ConversationStage.SUMMARY_GENERATED,
        summary_generated=True,
    )
    session.extracted_fields["tatva_user_id"] = "abc123"
    session.extracted_fields["client_name"] = "Navya"
    session.extracted_fields["email"] = "navya@gmail.com"
    session.flow_state["awaiting_returning_edit_decision"] = True

    sent_messages: list[str] = []

    async def fake_get_session(_session_id):
        return session

    async def fake_save_session(_session):
        return None

    async def fake_upsert_session_log(_session):
        return None

    async def fake_send_context_then_mcq_list(_phone, body, _step):
        sent_messages.append(body)

    async def fake_send_returning_user_reentry_prompt(_session, _phone):
        raise AssertionError("Welcome back should not fire again while awaiting edit decision")

    monkeypatch.setattr(wh, "get_session", fake_get_session)
    monkeypatch.setattr(wh, "save_session", fake_save_session)
    monkeypatch.setattr(wh.supabase_store, "upsert_session_log", fake_upsert_session_log)
    monkeypatch.setattr(wh, "send_context_then_mcq_list", fake_send_context_then_mcq_list)
    monkeypatch.setattr(wh, "_send_returning_user_reentry_prompt", fake_send_returning_user_reentry_prompt)

    await wh._handle_whatsapp_message_impl(
        "wa_test",
        "whatsapp:+91999",
        "hiiiii",
    )

    assert sent_messages == ["Please choose *Yes* or *No*."]


def test_sync_attachment_fields_can_hold_step_open():
    from backend.schemas.session import AttachmentMeta

    session = Session(
        session_id="wa_test",
        phone_number="whatsapp:+91999",
        channel="whatsapp",
        conversation_stage=ConversationStage.DETAIL_COLLECTION,
        service_category=ServiceCategory.ELECTRICAL,
        active_consultant="vivek",
    )
    se.on_service_selected(session, ServiceCategory.ELECTRICAL)
    for field, value in (
        ("service_q1", "new_wiring_rewiring"),
        ("service_q2", "residential_apartment"),
        ("service_q3", "urgent_breakdown_hazard"),
        ("service_q4", "Need rewiring"),
    ):
        se.mark_field_validated(session, field, value)
    session.attachments.append(
        AttachmentMeta(
            file_name="layout.png",
            file_url="https://example.com/layout.png",
            mime_type="image/png",
        )
    )
    session.flow_state["awaiting_more_upload_decision"] = True

    hybrid_flow.sync_attachment_fields(session, complete_step=False)

    assert session.extracted_fields.get("attachments") == "1 file uploaded"
    assert "attachments" not in session.completed_fields
    assert hybrid_flow.pending_file_upload(session) is True


@pytest.mark.asyncio
async def test_additional_file_upload_follow_up_advances_flow(monkeypatch):
    from backend.agents.chat import whatsapp_handler as wh

    session = Session(
        session_id="wa_whatsapp:+919888877777",
        phone_number="whatsapp:+919888877777",
        channel="whatsapp",
        conversation_stage=ConversationStage.DETAIL_COLLECTION,
        service_category=ServiceCategory.ELECTRICAL,
        active_consultant="vivek",
    )
    se.on_service_selected(session, ServiceCategory.ELECTRICAL)
    for field, value in (
        ("service_q1", "new_wiring_rewiring"),
        ("service_q2", "residential_apartment"),
        ("service_q3", "urgent_breakdown_hazard"),
        ("service_q4", "Need rewiring"),
    ):
        se.mark_field_validated(session, field, value)
    session.flow_state["media_upload_batch_version"] = 1
    session.flow_state["awaiting_additional_file_upload"] = True

    follow_up_calls: list[bool] = []

    async def fake_get_session(_session_id):
        return session

    async def fake_save_session(_session):
        return None

    async def fake_send_follow_up(_session, _phone, *, ask_for_more=True, **kwargs):
        follow_up_calls.append(ask_for_more)

    async def instant_sleep(_seconds):
        return None

    async def fake_upsert_session_log(_session):
        return None

    monkeypatch.setattr(wh, "get_session", fake_get_session)
    monkeypatch.setattr(wh, "save_session", fake_save_session)
    monkeypatch.setattr(wh, "_send_file_upload_follow_up", fake_send_follow_up)
    monkeypatch.setattr(wh.asyncio, "sleep", instant_sleep)
    monkeypatch.setattr(wh.supabase_store, "upsert_session_log", fake_upsert_session_log)

    await _debounced_file_upload_follow_up("wa_whatsapp:+919888877777", "whatsapp:+919888877777", 1)

    assert follow_up_calls == [False]
    assert "awaiting_additional_file_upload" not in session.flow_state


def test_strip_post_upload_follow_up_removes_file_prompt():
    session = Session(
        session_id="wa_test",
        phone_number="whatsapp:+91999",
        channel="whatsapp",
        conversation_stage=ConversationStage.DETAIL_COLLECTION,
        service_category=ServiceCategory.ELECTRICAL,
    )
    se.on_service_selected(session, ServiceCategory.ELECTRICAL)
    noisy = (
        "Thanks for sharing. Let us understand your requirements.\n\n"
        "Upload electrical layout, existing panel photos, or any related drawings.\n\n"
        "(Reply *skip* if nothing to upload.)"
    )
    cleaned = hybrid_flow.strip_post_upload_follow_up(session, noisy)
    assert "Thanks for sharing" not in cleaned
    assert "electrical layout" not in cleaned
    assert "skip" not in cleaned.lower()


@pytest.mark.asyncio
async def test_post_upload_follow_up_sends_ack_then_next_mcq_only(monkeypatch):
    from backend.agents.chat import whatsapp_handler as wh
    from backend.schemas.session import AttachmentMeta

    session = Session(
        session_id="wa_test",
        phone_number="whatsapp:+91999",
        channel="whatsapp",
        conversation_stage=ConversationStage.DETAIL_COLLECTION,
        service_category=ServiceCategory.ELECTRICAL,
    )
    se.on_service_selected(session, ServiceCategory.ELECTRICAL)
    for field, value in (
        ("service_q1", "new_wiring_rewiring"),
        ("service_q2", "residential_apartment"),
        ("service_q3", "urgent_breakdown_hazard"),
        ("service_q4", "Need rewiring"),
    ):
        se.mark_field_validated(session, field, value)
    session.flow_state["last_stage_shown"] = "service_questionnaire"
    session.flow_state["current_step_id"] = "service_q5"
    session.attachments.append(
        AttachmentMeta(
            file_name="plan.png",
            file_url="https://x/plan.png",
            mime_type="image/png",
        )
    )

    sent: list[tuple[str, object]] = []

    async def fake_send_context_then_mcq_list(_phone, context_body, step):
        sent.append((context_body, step))

    monkeypatch.setattr(wh, "send_context_then_mcq_list", fake_send_context_then_mcq_list)

    await wh._send_file_upload_follow_up(
        session,
        "whatsapp:+91999",
        ask_for_more=False,
    )

    assert len(sent) == 1
    context_body, _step = sent[0]
    assert context_body == "Thank you! We received your file."
    assert "Thanks for sharing" not in context_body
    assert "electrical layout" not in context_body


def test_complete_attachment_upload_skips_duplicate_stage_bridge():
    from backend.schemas.session import AttachmentMeta

    session = Session(
        session_id="wa_test",
        phone_number="whatsapp:+91999",
        channel="whatsapp",
        conversation_stage=ConversationStage.DETAIL_COLLECTION,
        service_category=ServiceCategory.ELECTRICAL,
    )
    se.on_service_selected(session, ServiceCategory.ELECTRICAL)
    session.flow_state["current_stage"] = "service_questionnaire"
    session.flow_state["last_stage_shown"] = "service_questionnaire"
    for field, value in (
        ("service_q1", "new_wiring_rewiring"),
        ("service_q2", "residential_apartment"),
        ("service_q3", "urgent_breakdown_hazard"),
        ("service_q4", "Need rewiring"),
    ):
        se.mark_field_validated(session, field, value)
    session.flow_state["current_step_id"] = "service_q5"
    session.attachments.append(
        AttachmentMeta(
            file_name="plan.png",
            file_url="https://x/plan.png",
            mime_type="image/png",
        )
    )

    msg = hybrid_flow.complete_attachment_upload(session)

    assert "Thanks for sharing" not in (msg or "")
    assert "electrical layout" not in (msg or "").lower()


def test_additional_file_upload_prompt_is_short():
    prompt = hybrid_flow.additional_file_upload_prompt()
    assert "upload" in prompt.lower()
    assert "Thanks for sharing" not in prompt
    assert "electrical layout" not in prompt.lower()


@pytest.mark.asyncio
async def test_yes_to_more_upload_sends_short_prompt(monkeypatch):
    from backend.agents.chat import whatsapp_handler as wh

    session = Session(
        session_id="wa_test",
        phone_number="whatsapp:+91999",
        channel="whatsapp",
        conversation_stage=ConversationStage.DETAIL_COLLECTION,
        service_category=ServiceCategory.ELECTRICAL,
    )
    se.on_service_selected(session, ServiceCategory.ELECTRICAL)
    session.flow_state["awaiting_more_upload_decision"] = True

    sent: list[str] = []

    async def fake_get_session(_session_id):
        return session

    async def fake_save_session(_session):
        return None

    async def fake_upsert_session_log(_session):
        return None

    async def fake_send_whatsapp_message(*, to, body):
        sent.append(body)

    monkeypatch.setattr(wh, "get_session", fake_get_session)
    monkeypatch.setattr(wh, "save_session", fake_save_session)
    monkeypatch.setattr(wh.supabase_store, "upsert_session_log", fake_upsert_session_log)
    monkeypatch.setattr(wh, "send_whatsapp_message", fake_send_whatsapp_message)

    await wh._handle_whatsapp_message_impl(
        "wa_test",
        "whatsapp:+91999",
        "yes",
        list_id="yes",
    )

    assert sent == [hybrid_flow.additional_file_upload_prompt()]
    assert session.flow_state.get("awaiting_additional_file_upload") is True


def test_greeting_detection_not_name_false_positive():
    assert is_greeting_message("Hiiii")
    assert is_greeting_message("Hello")
    assert is_greeting_message("Hi there")
    assert is_greeting_message("Hii bro")
    assert is_greeting_message("Hii anna")
    assert is_greeting_message("Namaste")
    assert is_greeting_message("Good Morning")
    assert not is_greeting_message("Hitesh")
    assert not is_greeting_message("Vidya")


@pytest.mark.asyncio
async def test_greeting_mid_flow_restarts_with_eva_intro():
    from backend.utils.session_idle import start_fresh_session
    from backend.storage.redis_store import save_session, get_session

    session_id = "wa_whatsapp:+919888877777"
    phone = "whatsapp:+919888877777"
    session = Session(
        session_id=session_id,
        phone_number=phone,
        channel="whatsapp",
        conversation_stage=ConversationStage.DETAIL_COLLECTION,
    )
    se.start_client_stage(session)
    session.add_message(MessageRole.ASSISTANT, hybrid_flow.first_client_message())
    se.mark_field_validated(session, "client_name", "Vidya")
    await save_session(session)

    await start_fresh_session(session_id, phone, reason="greeting_restart")
    session = await get_session(session_id)
    controller = ConversationController()
    resp = await controller.process_message(session, "Hii bro", channel="whatsapp")
    assert "I'm EVA" in resp.text
    assert "What is your full name?" in resp.text
    assert session.extracted_fields.get("client_name") != "Hii bro"
    assert "client_name" not in session.completed_fields

    resp2 = await controller.process_message(session, "Namaste", channel="whatsapp")
    assert "I'm EVA" in resp2.text
    assert "What is your full name?" in resp2.text


@pytest.mark.asyncio
async def test_greeting_mid_flow_does_not_advance_on_casual_hi():
    session = Session(
        session_id="wa_whatsapp:+919888877777",
        phone_number="whatsapp:+919888877777",
        channel="whatsapp",
        conversation_stage=ConversationStage.DETAIL_COLLECTION,
    )
    se.start_client_stage(session)
    session.add_message(MessageRole.ASSISTANT, hybrid_flow.first_client_message())

    controller = ConversationController()
    resp = await controller.process_message(session, "Hii bro", channel="whatsapp")
    assert "I'm EVA" in resp.text
    assert "What is your full name?" in resp.text
    assert "client_name" not in session.completed_fields


@pytest.mark.asyncio
async def test_name_after_restart45_does_not_repeat_eva_intro():
    session = Session(
        session_id="wa_whatsapp:+919999999999",
        phone_number="whatsapp:+919999999999",
        channel="whatsapp",
        conversation_stage=ConversationStage.ROUTING,
    )
    intro = hybrid_flow.first_client_message()
    session.add_message(MessageRole.ASSISTANT, intro)
    se.start_client_stage(session)

    controller = ConversationController()
    resp = await controller.process_message(session, "Divya", channel="whatsapp")
    assert "I'm EVA" not in resp.text
    assert "What is your full name?" not in resp.text
    assert "city" in resp.text.lower()
    assert session.extracted_fields.get("client_name") == "Divya"


@pytest.mark.asyncio
async def test_first_whatsapp_message_shows_eva_intro():
    session = Session(
        session_id="wa_whatsapp:+919999999999",
        phone_number="whatsapp:+919999999999",
        channel="whatsapp",
        conversation_stage=ConversationStage.ROUTING,
    )
    controller = ConversationController()
    resp = await controller.process_message(session, "Hiii", channel="whatsapp")
    assert "I'm EVA" in resp.text
    assert "What is your full name?" in resp.text
    assert session.extracted_fields.get("client_name") != "Hiii"


@pytest.mark.asyncio
async def test_thank_you_after_submit_does_not_restart_flow():
    session = Session(
        session_id="wa_whatsapp:+919999999999",
        phone_number="whatsapp:+919999999999",
        channel="whatsapp",
        conversation_stage=ConversationStage.SUMMARY_GENERATED,
        summary_generated=True,
    )
    controller = ConversationController()
    resp = await controller.process_message(session, "Thank you", channel="whatsapp")
    assert "I'm EVA" not in resp.text
    assert "You're welcome" in resp.text
    assert session.summary_generated is True


def test_nova_detect_service_by_number():
    assert detect_service("2") == ServiceCategory.HOME_INTERIORS
    assert detect_service("5") == ServiceCategory.SOLAR


def test_stage_order_strict():
    assert se.STAGE_ORDER.index("client_details") < se.STAGE_ORDER.index("service_selection")
    assert se.STAGE_ORDER.index("project_overview") < se.STAGE_ORDER.index("timeline")
    assert se.STAGE_ORDER.index("attachments") < se.STAGE_ORDER.index("final_review")


def test_client_stage_steps_only_client_fields():
    session = Session(session_id="t", phone_number="+1", conversation_stage=ConversationStage.ROUTING)
    se.start_client_stage(session)
    steps = hybrid_flow._steps_in_current_stage(session)
    assert all(s["stage"] == "client_details" for s in steps)
    assert steps[0]["field"] == "client_name"


def test_no_sqft_in_technical_stage():
    session = Session(
        session_id="t", phone_number="+1",
        service_category=ServiceCategory.PAINTING_WATERPROOFING,
        conversation_stage=ConversationStage.DETAIL_COLLECTION,
        active_consultant="manjunath",
    )
    se.on_service_selected(session, ServiceCategory.PAINTING_WATERPROOFING)
    session.flow_state["current_stage"] = "technical_specs"
    steps = hybrid_flow._steps_in_current_stage(session)
    fields = [s["field"] for s in steps]
    assert "overview_property_size" not in fields
    assert "tech_room_configuration" in fields


def test_three_option_mcq_uses_three_row_list(monkeypatch):
    from backend.config import get_settings
    from backend.intelligence.qualification_builder import enrich_mcq_step_for_whatsapp

    monkeypatch.setenv("TWILIO_MCQ_LIST_3_CONTENT_SID", "HX3row000000000000000000000000001")
    monkeypatch.setenv("TWILIO_MCQ_LIST_4_CONTENT_SID", "HX2def478cef646e98b157b87d5998c433")
    get_settings.cache_clear()

    step = {
        "type": "mcq",
        "field": "service_q1",
        "prompt": "What type of event?",
        "options": [
            {"label": "Wedding", "value": "wedding"},
            {"label": "Birthday Party", "value": "birthday"},
            {"label": "Corporate Event", "value": "corporate"},
        ],
    }
    enriched = enrich_mcq_step_for_whatsapp(step)
    assert enriched["twilio_content_sid"] == "HX3row000000000000000000000000001"
    assert enriched.get("twilio_list_slots") == 3


def test_farm_infrastructure_four_option_mcq_uses_clickable_list(monkeypatch):
    from backend.config import get_settings
    from backend.intelligence.qualification_builder import _service_questionnaire_steps

    monkeypatch.setenv("TWILIO_MCQ_LIST_4_CONTENT_SID", "HX2def478cef646e98b157b87d5998c433")
    get_settings.cache_clear()

    steps = _service_questionnaire_steps(ServiceCategory.FARM_INFRASTRUCTURE)
    q2 = next(s for s in steps if s["field"] == "service_q2")
    assert q2["prompt"] == "What is the land area for development?"
    assert q2["twilio_content_sid"] == "HX2def478cef646e98b157b87d5998c433"
    assert q2.get("twilio_list_slots") == 4


def test_farm_infrastructure_mcq_uses_correct_prompt_and_clickable_list(monkeypatch):
    from backend.config import get_settings
    from backend.intelligence.qualification_builder import _service_questionnaire_steps

    monkeypatch.setenv("TWILIO_MCQ_LIST_5_CONTENT_SID", "HXe51472b177c7bf1f3f2b0899b62af29f")
    get_settings.cache_clear()

    steps = _service_questionnaire_steps(ServiceCategory.FARM_INFRASTRUCTURE)
    q1 = next(s for s in steps if s["field"] == "service_q1")
    assert q1["prompt"] == "What type of farm infrastructure do you need?"
    assert q1["twilio_content_sid"] == "HXe51472b177c7bf1f3f2b0899b62af29f"
    assert q1.get("twilio_list_slots") == 5
    assert "interior project" not in q1["prompt"].lower()


def test_handoff_excludes_first_farm_question_when_interactive_list(monkeypatch):
    from backend.config import get_settings
    from backend.intelligence.hybrid_flow import append_first_step_to_handoff
    from backend.intelligence import stage_engine as se

    monkeypatch.setenv("TWILIO_MCQ_LIST_5_CONTENT_SID", "HXe51472b177c7bf1f3f2b0899b62af29f")
    get_settings.cache_clear()

    session = Session(
        session_id="wa_test",
        phone_number="whatsapp:+91999",
        channel="whatsapp",
        conversation_stage=ConversationStage.DETAIL_COLLECTION,
    )
    for field, value in (
        ("client_name", "Harshi"),
        ("phone_number", "+91999"),
        ("city", "Hyderabad"),
        ("property_location", "HSR"),
        ("preferred_contact_time", "morning"),
        ("willing_to_create_project", "yes"),
    ):
        se.mark_field_validated(session, field, value)
    se.mark_field_validated(session, "ava_intro_shown", True)
    se.on_service_selected(session, ServiceCategory.FARM_INFRASTRUCTURE)
    handoff = append_first_step_to_handoff(
        session,
        "Perfect ✨ I'm connecting you with Anil Reddy, our specialist.",
    )
    assert "farm infrastructure" not in handoff.lower()
    assert "interior project" not in handoff.lower()
    assert "select the service" not in handoff.lower()
    assert "Anil Reddy" in handoff


def test_home_interiors_mcq_uses_shared_dynamic_list(monkeypatch):
    from backend.config import get_settings
    from backend.intelligence.qualification_builder import _service_questionnaire_steps

    monkeypatch.setenv("TWILIO_MCQ_LIST_5_CONTENT_SID", "HXe51472b177c7bf1f3f2b0899b62af29f")
    get_settings.cache_clear()

    steps = _service_questionnaire_steps(ServiceCategory.HOME_INTERIORS)
    q1 = next(s for s in steps if s["field"] == "service_q1")
    assert q1["twilio_content_sid"] == "HXe51472b177c7bf1f3f2b0899b62af29f"
    assert q1.get("twilio_list_slots") == 5
    assert "interior project" in q1["prompt"].lower()


def test_willing_to_create_project_follows_contact_time():
    from backend.intelligence.qualification_builder import build_client_details_steps

    steps = build_client_details_steps()
    fields = [s["field"] for s in steps]
    assert fields.index("preferred_contact_time") < fields.index("willing_to_create_project")
    step = next(s for s in steps if s["field"] == "willing_to_create_project")
    assert step["prompt"].startswith("Would you like to proceed with creating your project?")
    assert [o["label"] for o in step["options"]] == ["Yes, Create My Project", "No, I'm Just Exploring"]


def test_willing_to_create_project_uses_two_row_list(monkeypatch):
    from backend.config import get_settings
    from backend.intelligence.qualification_builder import build_client_details_steps
    from backend.agents.chat.twilio_client import mcq_uses_interactive_delivery

    monkeypatch.setenv("TWILIO_MCQ_LIST_2_CONTENT_SID", "HX2row000000000000000000000000001")
    monkeypatch.setenv("TWILIO_WHATSAPP_QUICK_REPLY", "true")
    get_settings.cache_clear()

    step = next(s for s in build_client_details_steps() if s["field"] == "willing_to_create_project")
    assert step.get("twilio_content_sid") == "HX2row000000000000000000000000001"
    assert mcq_uses_interactive_delivery(step) is True


def test_project_declined_no_ends_chat():
    session = Session(
        session_id="t",
        phone_number="whatsapp:+91999",
        channel="whatsapp",
        conversation_stage=ConversationStage.DETAIL_COLLECTION,
    )
    se.start_client_stage(session)
    for field, value in (
        ("client_name", "Navya"),
        ("city", "Bengaluru"),
        ("property_location", "HSR Layout"),
        ("email", "skipped"),
        ("preferred_contact_time", "afternoon"),
    ):
        se.mark_field_validated(session, field, value)
    step = hybrid_flow.get_current_step(session)
    assert step is not None
    assert step["field"] == "willing_to_create_project"

    reply, handled = hybrid_flow.process_hybrid_turn(session, "no")
    assert handled is True
    assert "not looking to start a project" in reply.lower()
    assert "restart after 5 minutes" in reply.lower()
    assert session.flow_state.get("project_declined") is True
    assert not se.needs_service_selection(session)


def test_project_declined_reconcile_does_not_advance_to_service_selection():
    session = Session(
        session_id="t",
        phone_number="whatsapp:+91999",
        channel="whatsapp",
        conversation_stage=ConversationStage.DETAIL_COLLECTION,
    )
    se.start_client_stage(session)
    for field, value in (
        ("client_name", "Navya"),
        ("city", "Hyderabad"),
        ("property_location", "Bengaluru, hsr layout"),
        ("email", "skipped"),
        ("preferred_contact_time", "afternoon"),
    ):
        se.mark_field_validated(session, field, value)

    hybrid_flow.process_hybrid_turn(session, "no")
    se.reconcile_session(session)

    assert session.flow_state.get("project_declined") is True
    assert se.fs_current_stage(session) == "client_details"
    assert not se.needs_service_selection(session)


@pytest.mark.asyncio
async def test_persist_terminal_enquiry_saves_declined_lead(monkeypatch):
    from backend.storage import supabase_store

    session = Session(
        session_id="wa_declined",
        phone_number="whatsapp:+91999",
        channel="whatsapp",
        conversation_stage=ConversationStage.DETAIL_COLLECTION,
    )
    se.start_client_stage(session)
    for field, value in (
        ("client_name", "Navya"),
        ("city", "Hyderabad"),
        ("property_location", "Bengaluru, hsr layout"),
        ("email", "skipped"),
        ("preferred_contact_time", "afternoon"),
    ):
        se.mark_field_validated(session, field, value)
    hybrid_flow.process_hybrid_turn(session, "no")

    saved = []

    async def mock_save(s):
        saved.append(s)
        return True

    monkeypatch.setattr(supabase_store, "save_enquiry", mock_save)
    monkeypatch.setattr(supabase_store, "is_configured", lambda: True)

    assert await supabase_store.persist_terminal_enquiry(session) is True
    assert len(saved) == 1
    assert saved[0].extracted_fields.get("willing_to_create_project") == "no"
    assert saved[0].extracted_fields.get("client_name") == "Navya"


def test_project_declined_yes_continues_flow():
    session = Session(
        session_id="t",
        phone_number="whatsapp:+91999",
        channel="whatsapp",
        conversation_stage=ConversationStage.DETAIL_COLLECTION,
    )
    se.start_client_stage(session)
    for field, value in (
        ("client_name", "Navya"),
        ("city", "Bengaluru"),
        ("property_location", "HSR Layout"),
        ("email", "skipped"),
        ("preferred_contact_time", "afternoon"),
    ):
        se.mark_field_validated(session, field, value)

    reply, handled = hybrid_flow.process_hybrid_turn(session, "yes")
    assert handled is True
    assert session.flow_state.get("project_declined") is not True
    assert se.needs_service_selection(session)
    assert hybrid_flow.SERVICE_SELECTION_TRANSITION in reply or "service" in reply.lower()


@pytest.mark.asyncio
async def test_project_declined_follow_up_message():
    session = Session(
        session_id="wa_whatsapp:+91999",
        phone_number="whatsapp:+91999",
        channel="whatsapp",
        conversation_stage=ConversationStage.DETAIL_COLLECTION,
        flow_state={"project_declined": True, "conversation_ended": True},
    )
    controller = ConversationController()
    resp = await controller.process_message(session, "hello again", channel="whatsapp")
    assert "restart after 5 minutes" in resp.text.lower()


def test_preferred_contact_time_uses_whatsapp_list_template():
    from backend.intelligence.qualification_builder import build_client_details_steps
    from backend.agents.chat.twilio_client import mcq_uses_interactive_delivery

    step = next(s for s in build_client_details_steps() if s["field"] == "preferred_contact_time")
    assert "(only if Needed)" in step["prompt"]
    assert step["twilio_content_sid"] == "HX4e36328276831fc79aa5feb83f0b86a4"
    assert step.get("require_content_variables") is True
    assert step.get("twilio_list_prompt") == step["prompt"]
    assert mcq_uses_interactive_delivery(step) is True


def test_mcq_in_current_stage_only():
    session = Session(
        session_id="t", phone_number="+1",
        service_category=ServiceCategory.ELECTRICAL,
        conversation_stage=ConversationStage.DETAIL_COLLECTION,
        active_consultant="vivek",
    )
    se.start_client_stage(session)
    for f in ["client_name", "city", "property_location", "preferred_contact_time", "willing_to_create_project"]:
        session.mark_field_complete(f, "x")
    session.mark_field_complete("phone_number", "+1")
    se.mark_stage_complete(session, "client_details")
    se.on_service_selected(session, ServiceCategory.ELECTRICAL)
    session.flow_state["current_stage"] = "project_overview"
    step = hybrid_flow.get_current_step(session)
    assert step is not None
    assert step["stage"] == "project_overview"


def test_lead_scorer():
    session = Session(
        session_id="test",
        phone_number="+1",
        service_category=ServiceCategory.HOME_INTERIORS,
        conversation_stage=ConversationStage.SUMMARY_GENERATED,
        summary_generated=True,
    )
    session.completed_fields = se.required_fields_for_summary(session)
    score, tier = score_lead(session)
    assert 0 <= score <= 100
    assert tier in ("hot", "warm", "cold")


def test_after_client_details_transition_before_service_selection():
    session = Session(
        session_id="t",
        phone_number="whatsapp:+91999",
        channel="whatsapp",
        conversation_stage=ConversationStage.DETAIL_COLLECTION,
    )
    se.start_client_stage(session)
    for field, value in (
        ("client_name", "Vidya"),
        ("city", "Hyderabad"),
        ("property_location", "HSR"),
        ("email", "skipped"),
        ("preferred_contact_time", "evening"),
        ("willing_to_create_project", "yes"),
        ("phone_number", "+91999"),
    ):
        se.mark_field_validated(session, field, value)
    se.reconcile_session(session)
    assert se.fs_current_stage(session) == "service_selection"
    msg = hybrid_flow._next_step_message(session)
    assert msg == hybrid_flow.SERVICE_SELECTION_TRANSITION


def test_edit_file_action_uses_clickable_list(monkeypatch):
    from backend.config import get_settings
    from backend.intelligence import edit_flow
    from backend.intelligence.qualification_builder import enrich_mcq_step_for_whatsapp
    from backend.agents.chat.twilio_client import mcq_uses_interactive_delivery

    monkeypatch.setenv("TWILIO_MCQ_LIST_4_CONTENT_SID", "HX2def478cef646e98b157b87d5998c433")
    monkeypatch.setenv("TWILIO_WHATSAPP_QUICK_REPLY", "true")
    get_settings.cache_clear()

    step = edit_flow._pad_edit_mcq_for_whatsapp(edit_flow._file_action_step())
    enriched = enrich_mcq_step_for_whatsapp(step)
    assert enriched["twilio_content_sid"] == "HX2def478cef646e98b157b87d5998c433"
    assert len(enriched["options"]) == 4
    assert mcq_uses_interactive_delivery(enriched) is True
    assert "Add New File" not in str(enriched.get("prompt", ""))


def test_final_review_actions_uses_one_row_list(monkeypatch):
    from backend.config import get_settings
    from backend.intelligence.qualification_builder import (
        enrich_mcq_step_for_whatsapp,
        final_review_action_step,
        prepare_final_review_outbound,
    )
    from backend.agents.chat.twilio_client import mcq_uses_interactive_delivery

    monkeypatch.setenv("TWILIO_MCQ_LIST_1_CONTENT_SID", "HX1row000000000000000000000000001")
    monkeypatch.setenv("TWILIO_WHATSAPP_QUICK_REPLY", "true")
    get_settings.cache_clear()

    step = enrich_mcq_step_for_whatsapp(final_review_action_step())
    assert step["twilio_content_sid"] == "HX1row000000000000000000000000001"
    assert [o["label"] for o in step["options"]] == ["Confirm & Submit"]
    assert mcq_uses_interactive_delivery(step) is True

    session = Session(
        session_id="wa_test",
        phone_number="whatsapp:+91999",
        channel="whatsapp",
        conversation_stage=ConversationStage.CONFIRMATION,
    )
    prepare_final_review_outbound(session)
    assert session.flow_state.get("final_review_outbound_step")


@pytest.mark.asyncio
async def test_final_review_edit_details_not_available():
    from backend.intelligence import edit_flow

    session = _session_ready_for_service_selection()
    se.on_service_selected(session, ServiceCategory.SOLAR)
    for field, value in (
        ("service_q1", "off_grid"),
        ("service_q2", "residential"),
        ("service_q3", "1500_4000"),
        ("service_q4", "notes"),
        ("attachments", "skipped"),
    ):
        se.mark_field_validated(session, field, value)
    se.enter_final_review(session)

    controller = ConversationController()
    resp = await controller.process_message(session, "edit details", channel="whatsapp")
    assert "Sorry" in resp.text
    assert not edit_flow.is_active(session)


def test_edit_post_actions_uses_two_row_list_not_four(monkeypatch):
    from backend.config import get_settings
    from backend.intelligence import edit_flow
    from backend.intelligence.qualification_builder import enrich_mcq_step_for_whatsapp
    from backend.agents.chat.twilio_client import mcq_uses_interactive_delivery

    monkeypatch.setenv("TWILIO_MCQ_LIST_2_CONTENT_SID", "HX2row000000000000000000000000001")
    monkeypatch.setenv("TWILIO_MCQ_LIST_4_CONTENT_SID", "HX2def478cef646e98b157b87d5998c433")
    monkeypatch.setenv("TWILIO_WHATSAPP_QUICK_REPLY", "true")
    get_settings.cache_clear()

    step = edit_flow._pad_edit_mcq_for_whatsapp(edit_flow._post_edit_step())
    enriched = enrich_mcq_step_for_whatsapp(step)
    assert enriched["twilio_content_sid"] == "HX2row000000000000000000000000001"
    assert enriched.get("twilio_list_slots") == 2
    assert len(enriched["options"]) == 2
    labels = [o["label"] for o in enriched["options"]]
    assert labels == ["Confirm & Submit", "Edit Again"]
    assert mcq_uses_interactive_delivery(enriched) is True


def test_edit_post_actions_without_two_row_sid_avoids_four_row_template(monkeypatch):
    from backend.config import get_settings
    from backend.intelligence import edit_flow
    from backend.intelligence.qualification_builder import enrich_mcq_step_for_whatsapp
    from backend.agents.chat.twilio_client import mcq_uses_interactive_delivery

    monkeypatch.delenv("TWILIO_MCQ_LIST_2_CONTENT_SID", raising=False)
    monkeypatch.setenv("TWILIO_MCQ_LIST_4_CONTENT_SID", "HX2def478cef646e98b157b87d5998c433")
    monkeypatch.setenv("TWILIO_WHATSAPP_QUICK_REPLY", "true")
    get_settings.cache_clear()

    step = edit_flow._pad_edit_mcq_for_whatsapp(edit_flow._post_edit_step())
    enriched = enrich_mcq_step_for_whatsapp(step)
    assert enriched.get("twilio_content_sid") in (None, "")
    assert mcq_uses_interactive_delivery(enriched) is False


def test_edit_section_menu_uses_clickable_list(monkeypatch):
    from backend.config import get_settings
    from backend.intelligence import edit_flow

    monkeypatch.setenv("TWILIO_MCQ_LIST_4_CONTENT_SID", "HX2def478cef646e98b157b87d5998c433")
    monkeypatch.setenv("TWILIO_WHATSAPP_QUICK_REPLY", "true")
    get_settings.cache_clear()

    session = Session(
        session_id="wa_edit",
        phone_number="whatsapp:+91999",
        channel="whatsapp",
        conversation_stage=ConversationStage.CONFIRMATION,
    )
    msg, step = edit_flow.enter_edit_mode(session)
    assert step is not None
    assert step["twilio_content_sid"] == "HX2def478cef646e98b157b87d5998c433"
    assert step.get("twilio_list_slots") == 4
    assert "Service Selection" not in [o["label"] for o in step["options"]]
    assert "Client Details" not in msg
    assert "No problem" in msg
    assert "Which section would you like to update?" in msg


@pytest.mark.asyncio
async def test_thank_you_after_submit_does_not_reopen_final_review():
    session = Session(
        session_id="wa_whatsapp:+91999",
        phone_number="whatsapp:+91999",
        channel="whatsapp",
        conversation_stage=ConversationStage.SUMMARY_GENERATED,
        summary_generated=True,
        flow_state={
            "current_stage": "final_review",
            "final_review_shown": True,
            "final_review_outbound_step": {"field": "__final_review__", "type": "mcq"},
        },
    )
    controller = ConversationController()
    resp = await controller.process_message(session, "Thank u", channel="whatsapp")
    assert "You're welcome" in resp.text
    assert "look correct" not in resp.text.lower()


def test_service_menu_prompt():
    assert "1." in SERVICE_MENU_PROMPT


def test_invalid_mcq_reasks_current_question():
    session = Session(
        session_id="t",
        phone_number="whatsapp:+91999",
        channel="whatsapp",
        conversation_stage=ConversationStage.DETAIL_COLLECTION,
    )
    se.start_client_stage(session)
    for field, value in (
        ("client_name", "Rahul"),
        ("city", "Bengaluru"),
        ("property_location", "HSR Layout"),
        ("email", "skipped"),
    ):
        se.mark_field_validated(session, field, value)
    step = hybrid_flow.get_current_step(session)
    assert step is not None
    assert step["field"] == "preferred_contact_time"
    prompt_snippet = step["prompt"][:30]

    reply, handled = hybrid_flow.process_hybrid_turn(session, "morning")
    assert handled is True
    assert se.field_is_complete(session, "preferred_contact_time")
    step = hybrid_flow.get_current_step(session)
    assert step is not None
    assert step["field"] == "willing_to_create_project"

    reply, handled = hybrid_flow.process_hybrid_turn(session, "banana pizza random")
    assert handled is True
    assert "Sorry" in reply
    assert "create a project" in reply.lower()
    assert not se.field_is_complete(session, "willing_to_create_project")


def test_stale_whatsapp_list_tap_on_answered_question_is_rejected():
    """Re-tapping an old list-picker must not change a completed answer."""
    session = Session(
        session_id="t",
        phone_number="whatsapp:+91999",
        channel="whatsapp",
        conversation_stage=ConversationStage.DETAIL_COLLECTION,
    )
    se.start_client_stage(session)
    for field, value in (
        ("client_name", "Navya"),
        ("city", "Bengaluru"),
        ("property_location", "HSR Layout"),
        ("preferred_contact_time", "afternoon"),
        ("willing_to_create_project", "yes"),
    ):
        se.mark_field_validated(session, field, value)
    se.on_service_selected(session, ServiceCategory.RESIDENTIAL_CONSTRUCTION)
    se.mark_field_validated(session, "service_q1", "new_home_build")
    session.flow_state["current_step_id"] = "q2_budget_range"

    reply, handled = hybrid_flow.process_hybrid_turn(
        session,
        "Farmhouse / Villa Construction",
        list_id="farmhouse_villa_construction",
    )
    assert handled is True
    assert "already answered" in reply.lower()
    assert session.extracted_fields.get("service_q1") == "new_home_build"
    step = hybrid_flow.get_current_step(session)
    assert step is not None
    assert step["field"] == "service_q2"


def test_current_whatsapp_list_tap_still_accepted():
    session = Session(
        session_id="t",
        phone_number="whatsapp:+91999",
        channel="whatsapp",
        conversation_stage=ConversationStage.DETAIL_COLLECTION,
    )
    se.start_client_stage(session)
    for field, value in (
        ("client_name", "Navya"),
        ("city", "Bengaluru"),
        ("property_location", "HSR Layout"),
        ("preferred_contact_time", "afternoon"),
        ("willing_to_create_project", "yes"),
    ):
        se.mark_field_validated(session, field, value)
    se.on_service_selected(session, ServiceCategory.RESIDENTIAL_CONSTRUCTION)

    reply, handled = hybrid_flow.process_hybrid_turn(
        session,
        "New Home Build",
        list_id="new_home_build",
    )
    assert handled is True
    assert se.field_is_complete(session, "service_q1")
    assert session.extracted_fields.get("service_q1") == "new_home_build"
    assert hybrid_flow.get_current_step(session)["field"] == "service_q2"


@pytest.mark.asyncio
async def test_off_topic_during_mcq_reasks_not_guardrail():
    session = Session(
        session_id="wa_whatsapp:+919999999999",
        phone_number="whatsapp:+919999999999",
        channel="whatsapp",
        conversation_stage=ConversationStage.DETAIL_COLLECTION,
    )
    se.start_client_stage(session)
    for field, value in (
        ("client_name", "Rahul"),
        ("city", "Bengaluru"),
        ("property_location", "HSR Layout"),
        ("email", "skipped"),
    ):
        se.mark_field_validated(session, field, value)

    controller = ConversationController()
    resp = await controller.process_message(session, "what is the cricket score", channel="whatsapp")
    assert "Sorry" in resp.text
    assert "contact" in resp.text.lower()
    assert not se.field_is_complete(session, "preferred_contact_time")


def test_livestock_does_not_trigger_stock_off_topic():
    farm_answer = (
        "The goal is to develop a diversified farm with greenhouse or livestock units. "
        "Planned activities include dairy or poultry farming."
    )
    assert _is_off_topic(farm_answer) is False
    assert _is_off_topic("what is the stock market doing today") is True


@pytest.mark.asyncio
async def test_farm_descriptive_answer_not_guardrail_redirect():
    session = Session(
        session_id="wa_whatsapp:+919999999999",
        phone_number="whatsapp:+919999999999",
        channel="whatsapp",
        conversation_stage=ConversationStage.DETAIL_COLLECTION,
        service_category=ServiceCategory.FARM_INFRASTRUCTURE,
        active_consultant="anil",
    )
    for field, value in (
        ("client_name", "Vidya"),
        ("city", "Mysore"),
        ("property_location", "Mysore, kuvemunagar"),
        ("preferred_contact_time", "morning"),
        ("willing_to_create_project", "yes"),
        ("phone_number", "+919999999999"),
        ("ava_intro_shown", True),
    ):
        se.mark_field_validated(session, field, value)
    se.on_service_selected(session, ServiceCategory.FARM_INFRASTRUCTURE)
    for field, value in (
        ("service_q1", "integrated_farm_infrastructure"),
        ("service_q2", "1_5_acres"),
        ("service_q3", "yes_power_borewell"),
    ):
        se.mark_field_validated(session, field, value)
    se.reconcile_session(session)
    step = hybrid_flow.get_current_step(session)
    assert step is not None
    assert step["field"] == "service_q4"

    farm_answer = (
        "The farm is currently used for small-scale seasonal crop cultivation. "
        "The goal is to develop it into a diversified farm with livestock units, "
        "dairy or poultry farming, and reliable water supply."
    )
    controller = ConversationController()
    resp = await controller.process_message(session, farm_answer, channel="whatsapp")
    assert GUARDRAIL_REDIRECT not in resp.text
    assert "beautiful space" not in resp.text.lower()
    assert se.field_is_complete(session, "service_q4")
    assert "upload" in resp.text.lower() or "file" in resp.text.lower()


def _session_ready_for_service_selection() -> Session:
    session = Session(
        session_id="wa_whatsapp:+919999999999",
        phone_number="whatsapp:+919999999999",
        channel="whatsapp",
        conversation_stage=ConversationStage.DETAIL_COLLECTION,
    )
    se.start_client_stage(session)
    for field, value in (
        ("client_name", "Rahul"),
        ("city", "Bengaluru"),
        ("property_location", "HSR Layout"),
        ("preferred_contact_time", "morning"),
        ("willing_to_create_project", "yes"),
        ("phone_number", "+919999999999"),
    ):
        se.mark_field_validated(session, field, value)
    se.mark_stage_complete(session, "client_details")
    se.reconcile_session(session)
    assert se.needs_service_selection(session)
    return session


@pytest.mark.asyncio
async def test_invalid_service_selection_reasks():
    session = _session_ready_for_service_selection()

    controller = ConversationController()
    resp = await controller.process_message(session, "banana smoothie", channel="whatsapp")
    assert "Sorry" in resp.text
    assert session.service_category is None


@pytest.mark.asyncio
async def test_page2_service_selection_rejects_off_list_service():
    """Typing a page-1 service (e.g. interior) while on Choose Other Services must re-ask."""
    session = _session_ready_for_service_selection()
    session.flow_state["service_list_page"] = 2

    controller = ConversationController()
    resp = await controller.process_message(session, "interior", channel="whatsapp")
    assert "Sorry" in resp.text
    assert "Choose Other Services" in resp.text
    assert session.service_category is None
    assert session.flow_state.get("service_list_page") == 2


@pytest.mark.asyncio
async def test_page2_service_selection_accepts_list_option():
    from backend.schemas.service import ServiceCategory

    session = _session_ready_for_service_selection()
    session.flow_state["service_list_page"] = 2

    controller = ConversationController()
    resp = await controller.process_message(session, "solar", channel="whatsapp")
    assert session.service_category == ServiceCategory.SOLAR
    assert "Kavya" in resp.text


@pytest.mark.asyncio
async def test_page1_service_selection_rejects_page2_service():
    session = _session_ready_for_service_selection()

    controller = ConversationController()
    resp = await controller.process_message(session, "solar", channel="whatsapp")
    assert "Sorry" in resp.text
    assert session.service_category is None

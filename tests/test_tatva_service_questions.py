"""Tests for dynamic Tatva service questionnaire."""
import pytest

from backend.integrations.tatva_service_questions import (
    build_steps_from_api_questions,
    required_fields_from_steps,
    transform_api_question,
    load_questionnaire_for_session,
)
from backend.schemas.service import ServiceCategory
from backend.schemas.session import Session, ConversationStage
from backend.intelligence import stage_engine as se
from backend.intelligence import hybrid_flow
from backend.intelligence.conversation_controller import ConversationController


RESIDENTIAL_API_QUESTIONS = [
    {
        "_id": "6a0c5330d6df2140566fec39",
        "questionText": "What type of residential construction project are you planning?",
        "type": "mcq",
        "options": [
            {"label": "New Home Build", "value": "new home build"},
            {"label": "Commercial", "value": "commercial"},
        ],
        "isRequired": True,
        "isActive": True,
        "displayOrder": 1,
        "submitKey": "order_1",
    },
    {
        "_id": "6a0c53d8d6df2140566fec67",
        "questionText": "What is your estimated project budget range?",
        "type": "mcq",
        "options": [
            {"label": "Under ₹25 Lakhs", "value": "under ₹25 lakhs"},
        ],
        "isRequired": True,
        "isActive": True,
        "displayOrder": 2,
        "submitKey": "order_2",
    },
    {
        "_id": "6a0c56d5d6df2140566fed55",
        "questionText": "Describe your project.",
        "type": "description",
        "isRequired": True,
        "isActive": True,
        "displayOrder": 4,
        "submitKey": "order_4",
    },
    {
        "_id": "6a0c5712d6df2140566fed61",
        "questionText": "Upload supporting documents.",
        "type": "fileupload",
        "isRequired": True,
        "isActive": True,
        "displayOrder": 5,
        "submitKey": "order_5",
        "fileUploadField": "file_order_5",
    },
]


def test_transform_api_question_mcq():
    step = transform_api_question(RESIDENTIAL_API_QUESTIONS[0])
    assert step["type"] == "mcq"
    assert step["field"] == "order_1"
    assert step["prompt"].startswith("What type")
    assert len(step["options"]) == 2


def test_transform_api_question_fileupload():
    step = transform_api_question(RESIDENTIAL_API_QUESTIONS[3])
    assert step["type"] == "file_request"
    assert step["field"] == "file_order_5"


def test_build_steps_sorted_by_display_order():
    steps = build_steps_from_api_questions(list(reversed(RESIDENTIAL_API_QUESTIONS)))
    fields = [s["field"] for s in steps]
    assert fields == ["order_1", "order_2", "order_4", "file_order_5"]


def test_required_fields_from_steps():
    steps = build_steps_from_api_questions(RESIDENTIAL_API_QUESTIONS)
    assert required_fields_from_steps(steps) == [
        "order_1", "order_2", "order_4", "file_order_5",
    ]


@pytest.mark.asyncio
async def test_load_questionnaire_for_session_from_api(monkeypatch):
    async def fake_fetch(service_id, *, session_id="unknown"):
        return {
            "success": True,
            "data": {
                "serviceId": service_id,
                "serviceName": "Residential Construction",
                "questions": RESIDENTIAL_API_QUESTIONS,
            },
        }

    monkeypatch.setattr(
        "backend.integrations.tatva_service_questions.fetch_service_questions",
        fake_fetch,
    )

    session = Session(session_id="t", phone_number="whatsapp:+91999", channel="whatsapp")
    steps = await load_questionnaire_for_session(session, ServiceCategory.RESIDENTIAL_CONSTRUCTION)

    assert len(steps) == 4
    assert session.flow_state["questionnaire_source"] == "tatva_api"
    assert session.flow_state["service_questionnaire_required_fields"] == [
        "order_1", "order_2", "order_4", "file_order_5",
    ]
    assert session.extracted_fields["tatva_service_name"] == "Residential Construction"


@pytest.mark.asyncio
async def test_service_selection_loads_dynamic_questionnaire(monkeypatch):
    async def fake_load(session, category):
        steps = build_steps_from_api_questions(RESIDENTIAL_API_QUESTIONS)
        from backend.integrations.tatva_service_questions import sync_questionnaire_state
        sync_questionnaire_state(session, steps, source="tatva_api")
        return steps

    monkeypatch.setattr(
        "backend.intelligence.conversation_controller.load_questionnaire_for_session",
        fake_load,
    )

    session = Session(
        session_id="t",
        phone_number="whatsapp:+919876543210",
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
        ("willing_to_create_project", "yes"),
    ):
        se.mark_field_validated(session, field, value)

    controller = ConversationController()
    resp = await controller.process_message(
        session,
        "residential_construction",
        channel="whatsapp",
        list_id="residential_construction",
    )
    assert session.service_category == ServiceCategory.RESIDENTIAL_CONSTRUCTION
    assert session.flow_state.get("service_questionnaire_required_fields")
    step = hybrid_flow.get_current_step(session)
    assert step is not None
    assert step["field"] == "order_1"
    assert "Aravind" in resp.text or "Perfect" in resp.text


@pytest.mark.asyncio
async def test_dynamic_mcq_answer_advances_to_next_question(monkeypatch):
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
    steps = build_steps_from_api_questions(RESIDENTIAL_API_QUESTIONS)
    from backend.integrations.tatva_service_questions import sync_questionnaire_state
    sync_questionnaire_state(session, steps, source="tatva_api")
    se.reconcile_session(session)

    reply, handled = hybrid_flow.process_hybrid_turn(session, "new home build", list_id="new home build")
    assert handled is True
    assert se.field_is_complete(session, "order_1")
    next_step = hybrid_flow.get_current_step(session)
    assert next_step["field"] == "order_2"
    assert "budget" in reply.lower() or next_step["prompt"].lower().startswith("what is your")

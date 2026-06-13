"""Tests for Tatva register-phone integration."""
import pytest

from backend.integrations.tatva_users import (
    normalize_phone_for_tatva,
    register_phone_user,
    register_tatva_user_for_session,
    _extract_user_id,
)
from backend.schemas.session import Session, ConversationStage
from backend.intelligence import hybrid_flow
from backend.intelligence import stage_engine as se
from backend.intelligence.conversation_controller import ConversationController


def test_normalize_phone_for_tatva():
    assert normalize_phone_for_tatva("whatsapp:+919876543210") == "9876543210"
    assert normalize_phone_for_tatva("+919876543210") == "9876543210"
    assert normalize_phone_for_tatva("9876543210") == "9876543210"


def test_extract_user_id():
    payload = {
        "success": True,
        "data": {"user": {"_id": "6a2bd3e9e4f654faac0093de"}, "created": False},
    }
    assert _extract_user_id(payload) == "6a2bd3e9e4f654faac0093de"


@pytest.mark.asyncio
async def test_register_phone_user_success(monkeypatch):
    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "success": True,
                "message": "User already exists",
                "data": {
                    "user": {"_id": "6a2bd3e9e4f654faac0093de", "phoneNumber": "9876543210"},
                    "created": False,
                },
            }

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, url, json):
            assert url.endswith("/users/api/users/register-phone")
            assert json == {"phoneNumber": "9876543210"}
            return FakeResponse()

    monkeypatch.setattr(
        "backend.integrations.tatva_users.httpx.AsyncClient",
        lambda **kwargs: FakeClient(),
    )

    result = await register_phone_user("whatsapp:+919876543210", session_id="t1")
    assert result is not None
    assert result["data"]["user"]["_id"] == "6a2bd3e9e4f654faac0093de"


@pytest.mark.asyncio
async def test_register_tatva_user_for_session_stores_id(monkeypatch):
    async def fake_register(phone_number, *, session_id="unknown"):
        return {
            "success": True,
            "message": "User already exists",
            "data": {
                "user": {"_id": "6a2bd3e9e4f654faac0093de"},
                "created": False,
            },
        }

    monkeypatch.setattr(
        "backend.integrations.tatva_users.register_phone_user",
        fake_register,
    )

    session = Session(
        session_id="t",
        phone_number="whatsapp:+919876543210",
        channel="whatsapp",
    )
    await register_tatva_user_for_session(session)
    assert session.extracted_fields["tatva_user_id"] == "6a2bd3e9e4f654faac0093de"
    assert session.flow_state.get("tatva_user_registered") is True


@pytest.mark.asyncio
async def test_yes_on_create_project_triggers_registration(monkeypatch):
    called = {"count": 0}

    async def fake_register(session):
        called["count"] += 1
        session.extracted_fields["tatva_user_id"] = "6a2bd3e9e4f654faac0093de"

    monkeypatch.setattr(
        "backend.intelligence.conversation_controller.register_tatva_user_for_session",
        fake_register,
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
    ):
        se.mark_field_validated(session, field, value)

    controller = ConversationController()
    resp = await controller.process_message(session, "yes", channel="whatsapp")
    assert called["count"] == 1
    assert session.extracted_fields.get("tatva_user_id") == "6a2bd3e9e4f654faac0093de"
    assert resp.text
    assert se.needs_service_selection(session)

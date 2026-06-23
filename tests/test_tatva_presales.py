"""Tests for Tatva presales API on project decline."""
import pytest

from backend.integrations.tatva_presales import (
    PRESALES_PATH,
    build_presales_payload,
    submit_presales_on_project_decline,
)
from backend.intelligence import stage_engine as se
from backend.schemas.session import ConversationStage, Session


def test_build_presales_payload_maps_session_fields():
    session = Session(
        session_id="t",
        phone_number="whatsapp:+917795429685",
        channel="whatsapp",
    )
    session.extracted_fields.update({
        "client_name": "John Doe",
        "email": "john@example.com",
        "city": "Pune, Maharashtra",
        "property_location": "Baner, Pune",
    })

    payload = build_presales_payload(session)
    assert payload == {
        "name": "John Doe",
        "email": "john@example.com",
        "phoneNumber": "7795429685",
        "location": "Pune, Maharashtra",
        "propertyLocation": "Baner, Pune",
    }


@pytest.mark.asyncio
async def test_submit_presales_on_project_decline_posts_json(monkeypatch):
    captured: dict = {}

    async def fake_post(url, json=None, **kwargs):
        captured["url"] = url
        captured["json"] = json
        return type("R", (), {"raise_for_status": lambda self: None, "json": lambda self: {"success": True}})()

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, url, json=None):
            return await fake_post(url, json=json)

    monkeypatch.setattr("backend.integrations.tatva_presales.httpx.AsyncClient", lambda **kwargs: FakeClient())
    monkeypatch.setattr(
        "backend.integrations.tatva_presales.get_settings",
        lambda: type("S", (), {"tatva_users_api_base_url": "https://api.withtatva.ai", "admin_api_key": "secret"})(),
    )

    session = Session(
        session_id="t",
        phone_number="whatsapp:+917795429685",
        channel="whatsapp",
        conversation_stage=ConversationStage.DETAIL_COLLECTION,
    )
    session.extracted_fields.update({
        "client_name": "John Doe",
        "email": "john@example.com",
        "city": "Pune, Maharashtra",
        "property_location": "Baner, Pune",
    })
    session.flow_state["project_declined"] = True

    ok = await submit_presales_on_project_decline(session)
    assert ok is True
    assert captured["url"] == f"https://api.withtatva.ai{PRESALES_PATH}"
    assert captured["json"]["name"] == "John Doe"
    assert captured["json"]["phoneNumber"] == "7795429685"
    assert session.flow_state.get("tatva_presales_submitted") is True


@pytest.mark.asyncio
async def test_project_declined_no_triggers_presales_submit(monkeypatch):
    from backend.intelligence.conversation_controller import ConversationController

    calls: list[str] = []

    async def fake_submit(session):
        calls.append(session.session_id)
        return True

    async def fake_register(_session):
        return None

    monkeypatch.setattr(
        "backend.integrations.tatva_presales.submit_presales_on_project_decline",
        fake_submit,
    )
    monkeypatch.setattr(
        "backend.intelligence.conversation_controller.register_new_tatva_user_for_session",
        fake_register,
    )

    session = Session(
        session_id="wa_decline",
        phone_number="whatsapp:+91999",
        channel="whatsapp",
        conversation_stage=ConversationStage.DETAIL_COLLECTION,
    )
    se.start_client_stage(session)
    for field, value in (
        ("client_name", "Navya"),
        ("city", "Bengaluru"),
        ("property_location", "HSR Layout"),
        ("email", ""),
        ("preferred_contact_time", "afternoon"),
    ):
        se.mark_field_validated(session, field, value)

    controller = ConversationController()
    resp = await controller.process_message(session, "no", channel="whatsapp", list_id="no")

    assert calls == ["wa_decline"]
    assert session.flow_state.get("project_declined") is True
    assert "not looking to start a project" in (resp.text or "").lower()

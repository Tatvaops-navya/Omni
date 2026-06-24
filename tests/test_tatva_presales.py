"""Tests for Tatva presales API after create-project decision."""
import pytest

from backend.integrations.tatva_presales import (
    PRESALES_FLAG_HIGH,
    PRESALES_FLAG_LOW,
    PRESALES_PATH,
    build_presales_payload,
    presales_flag_for_project_choice,
    submit_presales_lead,
    submit_presales_on_project_decline,
)
from backend.intelligence import stage_engine as se
from backend.schemas.session import ConversationStage, Session


def test_presales_flag_for_project_choice():
    assert presales_flag_for_project_choice("yes") == PRESALES_FLAG_HIGH
    assert presales_flag_for_project_choice("no") == PRESALES_FLAG_LOW


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

    payload = build_presales_payload(session, flag=PRESALES_FLAG_LOW)
    assert payload == {
        "name": "John Doe",
        "email": "john@example.com",
        "phoneNumber": "7795429685",
        "location": "Pune, Maharashtra",
        "propertyLocation": "Baner, Pune",
        "flag": "low",
    }


@pytest.mark.asyncio
async def test_submit_presales_lead_posts_json(monkeypatch):
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
        "email": "",
        "city": "Pune, Maharashtra",
        "property_location": "Baner, Pune",
    })

    ok = await submit_presales_lead(session, flag=PRESALES_FLAG_LOW)
    assert ok is True
    assert captured["url"] == f"https://api.withtatva.ai{PRESALES_PATH}"
    assert captured["json"] == {
        "name": "John Doe",
        "email": "",
        "phoneNumber": "7795429685",
        "location": "Pune, Maharashtra",
        "propertyLocation": "Baner, Pune",
        "flag": "low",
    }
    assert session.flow_state.get("tatva_presales_submitted") is True


@pytest.mark.asyncio
async def test_submit_presales_on_project_decline_wrapper(monkeypatch):
    calls: list[str] = []

    async def fake_submit(session, *, flag):
        calls.append(flag)
        return True

    monkeypatch.setattr(
        "backend.integrations.tatva_presales.submit_presales_lead",
        fake_submit,
    )

    session = Session(session_id="t", phone_number="whatsapp:+91999", channel="whatsapp")
    session.flow_state["project_declined"] = True

    ok = await submit_presales_on_project_decline(session)
    assert ok is True
    assert calls == [PRESALES_FLAG_LOW]


@pytest.mark.asyncio
async def test_project_declined_no_triggers_register_and_presales(monkeypatch):
    from backend.intelligence.conversation_controller import ConversationController

    presales_calls: list[tuple[str, str]] = []
    register_calls: list[str] = []

    async def fake_presales(session, *, flag):
        presales_calls.append((session.session_id, flag))
        return True

    async def fake_register(session):
        register_calls.append(session.session_id)
        session.extracted_fields["tatva_user_id"] = "6a2bd3e9e4f654faac0093de"
        session.flow_state["tatva_user_registered"] = True
        return None

    monkeypatch.setattr(
        "backend.integrations.tatva_presales.submit_presales_lead",
        fake_presales,
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
    session.flow_state["tatva_needs_registration"] = True
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

    assert register_calls == ["wa_decline"]
    assert presales_calls == [("wa_decline", PRESALES_FLAG_LOW)]
    assert session.flow_state.get("project_declined") is True
    assert "thank you for exploring tatvaops" in (resp.text or "").lower()


@pytest.mark.asyncio
async def test_project_accepted_yes_triggers_register_and_presales(monkeypatch):
    from backend.intelligence.conversation_controller import ConversationController

    presales_calls: list[tuple[str, str]] = []
    register_calls: list[str] = []

    async def fake_presales(session, *, flag):
        presales_calls.append((session.session_id, flag))
        return True

    async def fake_register(session):
        register_calls.append(session.session_id)
        session.extracted_fields["tatva_user_id"] = "6a2bd3e9e4f654faac0093de"
        session.flow_state["tatva_user_registered"] = True
        return None

    monkeypatch.setattr(
        "backend.integrations.tatva_presales.submit_presales_lead",
        fake_presales,
    )
    monkeypatch.setattr(
        "backend.intelligence.conversation_controller.register_new_tatva_user_for_session",
        fake_register,
    )

    session = Session(
        session_id="wa_accept",
        phone_number="whatsapp:+91999",
        channel="whatsapp",
        conversation_stage=ConversationStage.DETAIL_COLLECTION,
    )
    session.flow_state["tatva_needs_registration"] = True
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
    await controller.process_message(session, "yes", channel="whatsapp", list_id="yes")

    assert register_calls == ["wa_accept"]
    assert presales_calls == [("wa_accept", PRESALES_FLAG_HIGH)]

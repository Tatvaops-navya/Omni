"""Tests for Tatva check-phone and register-phone integration."""
import pytest

from backend.integrations.tatva_users import (
    VENDOR_BLOCKED_MESSAGE,
    normalize_phone_for_tatva,
    register_phone_user,
    check_phone_user,
    check_tatva_phone_for_session,
    register_new_tatva_user_for_session,
    register_tatva_user_for_session,
    is_vendor_response,
    is_unregistered_phone_response,
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


def test_is_vendor_response():
    assert is_vendor_response({"data": {"isVendor": True}}) is True
    assert is_vendor_response({"data": {"isVendor": False}}) is False
    assert is_vendor_response({"data": {}}) is False


def test_is_unregistered_phone_response():
    assert is_unregistered_phone_response({
        "data": {
            "phoneNumber": "8639097638",
            "isUser": False,
            "isVendor": False,
            "user": None,
        }
    }) is True
    assert is_unregistered_phone_response({
        "data": {"isUser": True, "isVendor": False, "user": {"_id": "abc"}}
    }) is False


@pytest.mark.asyncio
async def test_check_phone_user_unregistered(monkeypatch):
    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "success": True,
                "message": "No user found for this phone number",
                "data": {
                    "phoneNumber": "9876543210",
                    "isUser": False,
                    "isVendor": False,
                    "user": None,
                },
            }

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, url, json):
            assert url.endswith("/users/api/users/check-phone")
            assert json == {"phoneNumber": "9876543210"}
            return FakeResponse()

    monkeypatch.setattr(
        "backend.integrations.tatva_users.httpx.AsyncClient",
        lambda **kwargs: FakeClient(),
    )

    result = await check_phone_user("whatsapp:+919876543210", session_id="t1")
    assert result is not None
    assert is_unregistered_phone_response(result)


@pytest.mark.asyncio
async def test_register_phone_user_with_profile(monkeypatch):
    captured = {}

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "success": True,
                "message": "User registered",
                "data": {
                    "user": {"_id": "6a2bd3e9e4f654faac0093de"},
                    "created": True,
                    "isVendor": False,
                },
            }

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, url, json):
            captured["url"] = url
            captured["json"] = json
            return FakeResponse()

    monkeypatch.setattr(
        "backend.integrations.tatva_users.httpx.AsyncClient",
        lambda **kwargs: FakeClient(),
    )

    result = await register_phone_user(
        "whatsapp:+919876543210",
        full_name="Navya Sharma",
        email="navya@gmail.com",
        session_id="t1",
    )
    assert result is not None
    assert captured["url"].endswith("/users/api/users/register-phone")
    assert captured["json"] == {
        "phoneNumber": "9876543210",
        "fullName": "Navya Sharma",
        "email": "navya@gmail.com",
    }


@pytest.mark.asyncio
async def test_check_tatva_phone_marks_unregistered(monkeypatch):
    async def fake_check(phone_number, *, session_id="unknown"):
        return {
            "success": True,
            "message": "No user found for this phone number",
            "data": {
                "phoneNumber": "9876543210",
                "isUser": False,
                "isVendor": False,
                "user": None,
            },
        }

    monkeypatch.setattr(
        "backend.integrations.tatva_users.check_phone_user",
        fake_check,
    )

    session = Session(
        session_id="t",
        phone_number="whatsapp:+919876543210",
        channel="whatsapp",
    )
    blocked = await check_tatva_phone_for_session(session)
    assert blocked is None
    assert session.flow_state.get("tatva_needs_registration") is True
    assert session.flow_state.get("tatva_phone_checked") is True
    assert "tatva_user_id" not in session.extracted_fields


@pytest.mark.asyncio
async def test_register_new_tatva_user_after_project_decision(monkeypatch):
    captured = {}

    async def fake_register(phone_number, *, full_name=None, email=None, session_id="unknown"):
        captured["phone"] = phone_number
        captured["full_name"] = full_name
        captured["email"] = email
        return {
            "success": True,
            "message": "User registered",
            "data": {
                "user": {"_id": "6a2bd3e9e4f654faac0093de"},
                "created": True,
                "isVendor": False,
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
    session.flow_state["tatva_needs_registration"] = True
    se.mark_field_validated(session, "client_name", "Navya Sharma")
    se.mark_field_validated(session, "email", "navya@gmail.com")
    se.mark_field_validated(session, "city", "Pune, Maharashtra")
    se.mark_field_validated(session, "property_location", "Baner, Pune")
    se.mark_field_validated(session, "preferred_contact_time", "morning")
    se.mark_field_validated(session, "willing_to_create_project", "no")

    blocked = await register_new_tatva_user_for_session(session)
    assert blocked is None
    assert session.extracted_fields["tatva_user_id"] == "6a2bd3e9e4f654faac0093de"
    assert session.flow_state.get("tatva_user_registered") is True
    assert captured["full_name"] == "Navya Sharma"
    assert captured["email"] == "navya@gmail.com"


@pytest.mark.asyncio
async def test_register_new_tatva_user_skips_before_project_decision(monkeypatch):
    called = {"count": 0}

    async def fake_register(*args, **kwargs):
        called["count"] += 1
        return None

    monkeypatch.setattr(
        "backend.integrations.tatva_users.register_phone_user",
        fake_register,
    )

    session = Session(
        session_id="t",
        phone_number="whatsapp:+919876543210",
        channel="whatsapp",
    )
    session.flow_state["tatva_needs_registration"] = True
    se.mark_field_validated(session, "client_name", "Navya Sharma")
    se.mark_field_validated(session, "email", "navya@gmail.com")
    se.mark_field_validated(session, "city", "Pune, Maharashtra")
    se.mark_field_validated(session, "property_location", "Baner, Pune")

    blocked = await register_new_tatva_user_for_session(session)
    assert blocked is None
    assert called["count"] == 0
    assert "tatva_user_id" not in session.extracted_fields


@pytest.mark.asyncio
async def test_register_new_tatva_user_skips_without_email_step(monkeypatch):
    called = {"count": 0}

    async def fake_register(*args, **kwargs):
        called["count"] += 1
        return None

    monkeypatch.setattr(
        "backend.integrations.tatva_users.register_phone_user",
        fake_register,
    )

    session = Session(
        session_id="t",
        phone_number="whatsapp:+919876543210",
        channel="whatsapp",
    )
    session.flow_state["tatva_needs_registration"] = True
    se.mark_field_validated(session, "client_name", "Navya Sharma")

    blocked = await register_new_tatva_user_for_session(session)
    assert blocked is None
    assert called["count"] == 0
    assert "tatva_user_id" not in session.extracted_fields


@pytest.mark.asyncio
async def test_check_tatva_phone_blocks_vendor(monkeypatch):
    async def fake_check(phone_number, *, session_id="unknown"):
        return {
            "success": True,
            "message": "Vendor found",
            "data": {
                "phoneNumber": "7409512633",
                "isUser": False,
                "isVendor": True,
                "user": {"_id": "6980502f12f88d68453fdbd3"},
            },
        }

    monkeypatch.setattr(
        "backend.integrations.tatva_users.check_phone_user",
        fake_check,
    )

    session = Session(
        session_id="t",
        phone_number="whatsapp:+917409512633",
        channel="whatsapp",
    )
    blocked = await check_tatva_phone_for_session(session)
    assert blocked == VENDOR_BLOCKED_MESSAGE
    assert session.flow_state.get("vendor_blocked") is True
    assert "tatva_user_id" not in session.extracted_fields


@pytest.mark.asyncio
async def test_first_message_triggers_phone_check(monkeypatch):
    called = {"count": 0}

    async def fake_check(session):
        called["count"] += 1
        session.flow_state["tatva_needs_registration"] = True
        session.flow_state["tatva_phone_checked"] = True
        return None

    monkeypatch.setattr(
        "backend.intelligence.conversation_controller.check_tatva_phone_for_session",
        fake_check,
    )

    session = Session(
        session_id="t",
        phone_number="whatsapp:+919876543210",
        channel="whatsapp",
        conversation_stage=ConversationStage.ROUTING,
    )

    controller = ConversationController()
    resp = await controller.process_message(session, "Hi", channel="whatsapp")
    assert called["count"] == 1
    assert session.flow_state.get("tatva_needs_registration") is True
    assert "tatva_user_id" not in session.extracted_fields
    assert "EVA" in resp.text or "TatvaOps" in resp.text


@pytest.mark.asyncio
async def test_vendor_blocked_on_first_message(monkeypatch):
    async def fake_check(session):
        session.flow_state["vendor_blocked"] = True
        session.flow_state["conversation_ended"] = True
        return VENDOR_BLOCKED_MESSAGE

    monkeypatch.setattr(
        "backend.intelligence.conversation_controller.check_tatva_phone_for_session",
        fake_check,
    )

    session = Session(
        session_id="t",
        phone_number="whatsapp:+917409512633",
        channel="whatsapp",
        conversation_stage=ConversationStage.ROUTING,
    )

    controller = ConversationController()
    resp = await controller.process_message(session, "Hello", channel="whatsapp")
    assert "vendor" in resp.text.lower()
    assert session.flow_state.get("vendor_blocked") is True


@pytest.mark.asyncio
async def test_check_tatva_phone_hydrates_existing_user(monkeypatch):
    async def fake_check(phone_number, *, session_id="unknown"):
        return {
            "success": True,
            "message": "User already exists",
            "data": {
                "user": {
                    "_id": "698045af7d79fe3c880dab0f",
                    "phoneNumber": "8959896246",
                    "email": "pramod.d@tatvaops.com",
                    "fullName": "John Doe",
                },
                "created": False,
                "isUser": True,
                "isVendor": False,
            },
        }

    monkeypatch.setattr(
        "backend.integrations.tatva_users.check_phone_user",
        fake_check,
    )

    session = Session(
        session_id="t",
        phone_number="whatsapp:+918959896246",
        channel="whatsapp",
    )
    blocked = await check_tatva_phone_for_session(session)
    assert blocked is None
    assert session.flow_state.get("tatva_phone_is_user") is True
    assert session.extracted_fields["tatva_user_id"] == "698045af7d79fe3c880dab0f"
    assert session.extracted_fields["client_name"] == "John Doe"
    assert session.extracted_fields["email"] == "pramod.d@tatvaops.com"
    assert session.flow_state.get("tatva_needs_registration") is False


@pytest.mark.asyncio
async def test_existing_user_no_edit_continues_to_project_creation():
    from backend.integrations.returning_user_flow import prepare_returning_user_for_project_decision

    session = Session(
        session_id="t",
        phone_number="whatsapp:+918959896246",
        channel="whatsapp",
    )
    session.extracted_fields["tatva_user_id"] = "698045af7d79fe3c880dab0f"
    session.extracted_fields["client_name"] = "John Doe"
    session.extracted_fields["email"] = "pramod.d@tatvaops.com"

    msg = prepare_returning_user_for_project_decision(session)
    assert "which city" in msg.lower()
    assert se.field_is_complete(session, "client_name")
    assert not se.field_is_complete(session, "city")
    assert not se.field_is_complete(session, "property_location")
    step = hybrid_flow.get_current_step(session)
    assert step is not None
    assert step.get("field") == "city"


@pytest.mark.asyncio
async def test_first_message_existing_user_gets_welcome(monkeypatch):
    async def fake_check(session):
        session.flow_state["tatva_phone_checked"] = True
        session.flow_state["tatva_phone_is_user"] = True
        session.extracted_fields["tatva_user_id"] = "698045af7d79fe3c880dab0f"
        session.extracted_fields["client_name"] = "John Doe"
        return None

    monkeypatch.setattr(
        "backend.intelligence.conversation_controller.check_tatva_phone_for_session",
        fake_check,
    )

    session = Session(
        session_id="t",
        phone_number="whatsapp:+918959896246",
        channel="whatsapp",
        conversation_stage=ConversationStage.ROUTING,
    )

    controller = ConversationController()
    resp = await controller.process_message(session, "Hi", channel="whatsapp")
    assert "Hi there John Doe" in resp.text
    assert session.flow_state.get("awaiting_returning_location_decision") is True
    pending = session.flow_state.get("pending_outbound_mcq") or {}
    assert pending.get("field") == "__returning_location__"


@pytest.mark.asyncio
async def test_hydrate_returning_user_profile_uses_tatva_check_phone_only(monkeypatch):
    from backend.integrations.tatva_users import hydrate_returning_user_profile

    async def fake_check(phone_number, *, session_id="unknown"):
        return {
            "success": True,
            "data": {
                "isUser": True,
                "isVendor": False,
                "user": {
                    "_id": "6a3516e9122d62e1c4bc1fb5",
                    "phoneNumber": "8639097638",
                    "fullName": "Navya shree",
                    "city": "hyderabad",
                    "propertyLocation": "Hyderabad , Miyapur",
                },
            },
        }

    async def fake_load_addresses(session, *, force=False):
        session.flow_state["tatva_user_addresses"] = []
        session.flow_state["tatva_addresses_fetched"] = True
        session.flow_state["tatva_addresses_api_empty"] = True
        return []

    monkeypatch.setattr(
        "backend.integrations.tatva_users.check_phone_user",
        fake_check,
    )
    monkeypatch.setattr(
        "backend.integrations.tatva_user_addresses.load_user_addresses_for_session",
        fake_load_addresses,
    )

    session = Session(
        session_id="t",
        phone_number="whatsapp:+918639097638",
        channel="whatsapp",
    )
    await hydrate_returning_user_profile(session, force=True)
    assert session.extracted_fields["tatva_user_id"] == "6a3516e9122d62e1c4bc1fb5"
    assert session.extracted_fields.get("client_name") == "Navya shree"
    assert session.extracted_fields.get("city") == "hyderabad"
    assert session.extracted_fields.get("property_location") == "Hyderabad , Miyapur"


@pytest.mark.asyncio
async def test_hydrate_overwrites_placeholder_client_name(monkeypatch):
    from backend.integrations.returning_user_flow import RETURNING_MISSING_NAME_PLACEHOLDER
    from backend.integrations.tatva_users import hydrate_returning_user_profile
    from backend.intelligence import stage_engine as se

    async def fake_check(phone_number, *, session_id="unknown"):
        return {
            "success": True,
            "data": {
                "isUser": True,
                "isVendor": False,
                "user": {
                    "_id": "abc",
                    "fullName": "Navya shree",
                },
            },
        }

    async def fake_load_addresses(session, *, force=False):
        return []

    monkeypatch.setattr("backend.integrations.tatva_users.check_phone_user", fake_check)
    monkeypatch.setattr(
        "backend.integrations.tatva_user_addresses.load_user_addresses_for_session",
        fake_load_addresses,
    )

    session = Session(
        session_id="t",
        phone_number="whatsapp:+918639097638",
        channel="whatsapp",
    )
    se.mark_field_validated(session, "client_name", RETURNING_MISSING_NAME_PLACEHOLDER)
    await hydrate_returning_user_profile(session, force=True)
    assert session.extracted_fields.get("client_name") == "Navya shree"


@pytest.mark.asyncio
async def test_hydrate_force_overwrites_stale_email(monkeypatch):
    from backend.integrations.tatva_users import hydrate_returning_user_profile
    from backend.intelligence import stage_engine as se

    async def fake_check(phone_number, *, session_id="unknown"):
        return {
            "success": True,
            "data": {
                "isUser": True,
                "isVendor": False,
                "user": {
                    "_id": "abc",
                    "fullName": "Madhunala Navya shree",
                    "email": "navya.updated@gmail.com",
                },
            },
        }

    async def fake_load_addresses(session, *, force=False):
        return []

    monkeypatch.setattr("backend.integrations.tatva_users.check_phone_user", fake_check)
    monkeypatch.setattr(
        "backend.integrations.tatva_user_addresses.load_user_addresses_for_session",
        fake_load_addresses,
    )

    session = Session(
        session_id="t",
        phone_number="whatsapp:+918639097638",
        channel="whatsapp",
    )
    se.mark_field_validated(session, "client_name", "madhunala")
    se.mark_field_validated(session, "email", "")

    await hydrate_returning_user_profile(session, force=True)
    assert session.extracted_fields.get("client_name") == "Madhunala Navya shree"
    assert session.extracted_fields.get("email") == "navya.updated@gmail.com"


@pytest.mark.asyncio
async def test_yes_on_create_project_does_not_register(monkeypatch):
    called = {"count": 0}

    async def fake_register(session):
        called["count"] += 1
        session.extracted_fields["tatva_user_id"] = "6a2bd3e9e4f654faac0093de"
        return None

    monkeypatch.setattr(
        "backend.intelligence.conversation_controller.register_new_tatva_user_for_session",
        fake_register,
    )

    session = Session(
        session_id="t",
        phone_number="whatsapp:+919876543210",
        channel="whatsapp",
        conversation_stage=ConversationStage.DETAIL_COLLECTION,
    )
    se.start_client_stage(session)
    session.flow_state["tatva_phone_checked"] = True
    session.flow_state["tatva_user_registered"] = True
    session.extracted_fields["tatva_user_id"] = "6a2bd3e9e4f654faac0093de"
    for field, value in (
        ("client_name", "Navya"),
        ("email", "navya@gmail.com"),
        ("city", "Bengaluru"),
        ("property_location", "HSR Layout"),
        ("preferred_contact_time", "afternoon"),
    ):
        se.mark_field_validated(session, field, value)

    controller = ConversationController()
    resp = await controller.process_message(session, "yes", channel="whatsapp")
    assert called["count"] == 0
    assert resp.text
    assert se.needs_service_selection(session)

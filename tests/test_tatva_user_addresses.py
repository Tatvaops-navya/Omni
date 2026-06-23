"""Tests for Tatva user address API integration."""
import pytest

from backend.integrations.tatva_user_addresses import (
    normalize_user_addresses,
    profile_fields_from_address,
    saved_addresses_display,
)
from backend.integrations.returning_user_flow import (
    returning_saved_location_step,
    parse_returning_location_choice,
    apply_returning_location_choice,
    RETURNING_LOCATION_FIELD,
    saved_location_display,
)
from backend.schemas.session import Session


SAMPLE_ADDRESSES = [
    {
        "_id": "69d393184d8aa84fc60b95b1",
        "formattedAddress": "123 MG Road, Bangalore, Karnataka 560001",
        "locality": "Ashok Nagar",
        "district": "Bangalore Urban",
        "isDefault": True,
        "subTypeLabel": "Office",
    },
    {
        "_id": "69ca149a76447fb2e241a65d",
        "formattedAddress": "383, 9th Main Rd, HSR Layout, Bengaluru, Karnataka 560102, India",
        "locality": "Bengaluru",
        "district": "Bengaluru Urban",
        "isDefault": False,
        "subTypeLabel": "Work",
    },
]


def test_profile_fields_from_address_maps_location_and_property():
    fields = profile_fields_from_address({
        "formattedAddress": "Baner, Pune, Maharashtra 411045",
        "locality": "Baner",
        "district": "Pune",
        "state": "Maharashtra",
    })
    assert fields["city"] == "Pune, Maharashtra"
    assert fields["property_location"] == "Baner, Pune"


def test_normalize_keeps_all_formatted_addresses():
    raw = SAMPLE_ADDRESSES + [
        {
            "_id": "dup",
            "formattedAddress": "123 MG Road, Bangalore, Karnataka 560001",
            "isDefault": False,
        }
    ]
    result = normalize_user_addresses(raw)
    assert len(result) == 3
    assert result[0]["_id"] == "69d393184d8aa84fc60b95b1"


def test_saved_addresses_display_uses_formatted_address_only():
    session = Session(session_id="t", phone_number="+1", channel="whatsapp")
    session.flow_state["tatva_user_addresses"] = [
        {
            "_id": "6a3819cd122d62e1c4bc2caf",
            "formattedAddress": "6-2-881, kharthibad, 2nd floor, hyderabad, hyderabad, Telangana, 500004",
            "subType": "WORK",
            "isDefault": False,
        },
        {
            "_id": "6a38196e122d62e1c4bc2ca4",
            "formattedAddress": "883, 24th Cross Rd, Manjunatha Layout, 7th Sector, HSR Layout, Bengaluru, Karnataka 560102, India",
            "subType": "HOME",
            "isDefault": False,
        },
    ]
    text = saved_addresses_display(session)
    assert "6-2-881, kharthibad, 2nd floor, hyderabad, hyderabad, Telangana, 500004" in text
    assert "883, 24th Cross Rd, Manjunatha Layout" in text
    assert "WORK:" not in text
    assert "HOME:" not in text


def test_saved_addresses_display_lists_all():
    session = Session(session_id="t", phone_number="+1", channel="whatsapp")
    session.flow_state["tatva_user_addresses"] = SAMPLE_ADDRESSES
    text = saved_addresses_display(session)
    assert "123 MG Road" in text
    assert "HSR Layout" in text
    assert "(Default)" in text


def test_returning_saved_location_step_uses_address_options():
    session = Session(session_id="t", phone_number="+1", channel="whatsapp")
    session.flow_state["tatva_user_addresses"] = SAMPLE_ADDRESSES
    step = returning_saved_location_step(session)
    assert step["field"] == RETURNING_LOCATION_FIELD
    assert "Here are your saved locations" in step["prompt"]
    assert "123 MG Road" in step["prompt"]
    labels = [o["label"] for o in step["options"]]
    assert labels == ["Address 1", "Address 2", "Other address"]
    values = [o["value"] for o in step["options"]]
    assert values[-1] == "add_new_location"
    assert "69d393184d8aa84fc60b95b1" in values


def test_returning_location_enrich_keeps_other_address_in_list(monkeypatch):
    from backend.agents.chat.twilio_client import enrich_whatsapp_mcq_step, _is_other_option

    assert _is_other_option({"label": "Other address", "value": "add_new_location"}) is False

    session = Session(session_id="t", phone_number="+1", channel="whatsapp")
    session.flow_state["tatva_user_addresses"] = SAMPLE_ADDRESSES[:1]
    step = returning_saved_location_step(session)
    monkeypatch.setattr(
        "backend.agents.chat.twilio_client.settings.twilio_whatsapp_quick_reply",
        True,
    )
    monkeypatch.setattr(
        "backend.agents.chat.twilio_client.settings.twilio_mcq_list_2_content_sid",
        "HXtest2row",
    )
    enriched = enrich_whatsapp_mcq_step(step)
    assert enriched.get("twilio_content_sid") == "HXtest2row"
    assert [o["label"] for o in enriched["options"]] == ["Address 1", "Other address"]


def test_parse_address_short_label_selection():
    session = Session(session_id="t", phone_number="+1", channel="whatsapp")
    session.flow_state["tatva_user_addresses"] = SAMPLE_ADDRESSES
    assert parse_returning_location_choice("Address 2", session=session) == "69ca149a76447fb2e241a65d"
    assert parse_returning_location_choice("2", session=session) == "69ca149a76447fb2e241a65d"


def test_parse_location_from_quoted_multiline_reply():
    session = Session(session_id="t", phone_number="+1", channel="whatsapp")
    session.flow_state["tatva_user_addresses"] = SAMPLE_ADDRESSES
    quoted = (
        "Hi there 👋 Great to see you again!\n"
        "Choose your saved location\n"
        "Address 1"
    )
    assert parse_returning_location_choice(quoted, session=session) == "69d393184d8aa84fc60b95b1"


def test_parse_and_apply_address_selection():
    session = Session(session_id="t", phone_number="+1", channel="whatsapp")
    session.flow_state["tatva_user_addresses"] = SAMPLE_ADDRESSES
    choice = parse_returning_location_choice(
        "",
        list_id="69ca149a76447fb2e241a65d",
        session=session,
    )
    assert choice == "69ca149a76447fb2e241a65d"
    apply_returning_location_choice(session, choice)
    assert session.extracted_fields["city"] == "Bengaluru Urban"
    assert session.extracted_fields["property_location"] == "Bengaluru, Bengaluru Urban"


@pytest.mark.asyncio
async def test_send_returning_location_prompt_uses_context_then_list(monkeypatch):
    from backend.agents.chat import whatsapp_handler as wh

    session = Session(session_id="t", phone_number="whatsapp:+91999", channel="whatsapp")
    session.extracted_fields["tatva_user_id"] = "user123"
    session.flow_state["tatva_user_addresses"] = SAMPLE_ADDRESSES
    context_calls: list[str] = []

    async def fake_load(_session, *, force=False):
        return SAMPLE_ADDRESSES

    async def fake_send_context_then_mcq_list(_phone, context_body, step):
        context_calls.append(context_body)
        assert "123 MG Road" in context_body
        assert step["options"][0]["label"] == "Address 1"
        return True

    async def fake_save_session(_session):
        return None

    async def fake_upsert_session_log(_session):
        return None

    monkeypatch.setattr(
        "backend.integrations.tatva_user_addresses.load_user_addresses_for_session",
        fake_load,
    )
    monkeypatch.setattr(wh, "send_context_then_mcq_list", fake_send_context_then_mcq_list)
    monkeypatch.setattr(wh, "save_session", fake_save_session)
    monkeypatch.setattr(wh.supabase_store, "upsert_session_log", fake_upsert_session_log)
    monkeypatch.setenv("TWILIO_MCQ_LIST_3_CONTENT_SID", "HX3row000000000000000000000000001")
    monkeypatch.setenv("TWILIO_WHATSAPP_QUICK_REPLY", "true")
    from backend.config import get_settings
    get_settings.cache_clear()

    await wh._send_returning_location_prompt(session, "whatsapp:+91999")

    assert len(context_calls) == 1
    assert session.flow_state.get("awaiting_returning_location_decision") is True


@pytest.mark.asyncio
async def test_returning_location_prompt_without_addresses_asks_city(monkeypatch):
    from backend.agents.chat import whatsapp_handler as wh

    session = Session(
        session_id="wa_test",
        phone_number="whatsapp:+91999",
        channel="whatsapp",
    )
    session.extracted_fields.update({
        "client_name": "Navya",
        "tatva_user_id": "user123",
    })

    sent_messages: list[str] = []
    detail_calls: list[dict] = []

    async def fake_load(_session, *, force=False):
        return []

    async def fake_save_session(_session):
        return None

    async def fake_upsert_session_log(_session):
        return None

    async def fake_send_whatsapp_message(*, to, body):
        sent_messages.append(body)
        return True

    async def fake_send_detail(_session, phone, step):
        detail_calls.append(step)

    monkeypatch.setattr(
        "backend.integrations.tatva_user_addresses.load_user_addresses_for_session",
        fake_load,
    )
    monkeypatch.setattr(wh, "save_session", fake_save_session)
    monkeypatch.setattr(wh.supabase_store, "upsert_session_log", fake_upsert_session_log)
    monkeypatch.setattr(wh, "send_whatsapp_message", fake_send_whatsapp_message)
    monkeypatch.setattr(wh, "_send_client_detail_step_prompt", fake_send_detail)

    await wh._send_returning_location_prompt(session, "whatsapp:+91999")

    assert sent_messages == []
    assert detail_calls
    assert detail_calls[0].get("field") == "city"
    assert session.flow_state.get("awaiting_returning_location_decision") is not True


def test_returning_saved_location_step_profile_empty_api_message():
    from backend.integrations.returning_user_flow import returning_saved_location_step
    from backend.integrations.tatva_user_addresses import NO_RESPONSE_FROM_API

    session = Session(session_id="t", phone_number="+1", channel="whatsapp")
    session.extracted_fields.update({
        "tatva_user_id": "user123",
    })
    session.flow_state["tatva_addresses_api_empty"] = True
    step = returning_saved_location_step(session)
    assert step is None
    assert NO_RESPONSE_FROM_API in saved_location_display(session)


@pytest.mark.asyncio
async def test_send_context_then_mcq_list_skips_duplicate_context(monkeypatch):
    from backend.agents.chat import twilio_client as tc

    sent: list[str] = []

    async def fake_send_whatsapp_message(to, body):
        sent.append(body)
        return True

    async def fake_send_whatsapp_flow(to, body, step=None):
        sent.append(body)
        return True

    monkeypatch.setattr(tc, "send_whatsapp_message", fake_send_whatsapp_message)
    monkeypatch.setattr(tc, "send_whatsapp_flow", fake_send_whatsapp_flow)
    monkeypatch.setattr(tc, "enrich_whatsapp_mcq_step", lambda s: s)
    monkeypatch.setattr(tc, "mcq_uses_interactive_delivery", lambda _s: True)

    context = "Here is your saved location:\n\nCity: Hyderabad"
    step = {
        "type": "mcq",
        "prompt": context,
        "twilio_list_prompt": "Is this your location?",
        "options": [{"label": "Yes", "value": "yes"}],
    }
    await tc.send_context_then_mcq_list("+1", context, step)

    assert sent == [context, "Is this your location?"]


@pytest.mark.asyncio
async def test_claim_inbound_message_deduplicates_sid():
    from backend.storage.redis_store import claim_inbound_message, get_redis_store

    class _NoRedis:
        def is_configured(self):
            return False

    store = get_redis_store()
    original = store.is_configured
    store.is_configured = lambda: False
    try:
        sid = "SM_test_duplicate_123"
        assert await claim_inbound_message(sid, phone_number="+1", user_message="hii") is True
        assert await claim_inbound_message(sid, phone_number="+1", user_message="hii") is False
    finally:
        store.is_configured = original


@pytest.mark.asyncio
async def test_claim_inbound_message_deduplicates_body_bucket(monkeypatch):
    from backend.storage.redis_store import claim_inbound_message, get_redis_store, _idempotency_memory

    _idempotency_memory.clear()
    store = get_redis_store()
    store.is_configured = lambda: False
    monkeypatch.setattr("time.time", lambda: 1000.0)

    assert await claim_inbound_message("SM_one", phone_number="whatsapp:+1", user_message="hii") is True
    assert await claim_inbound_message("SM_two", phone_number="whatsapp:+1", user_message="hii") is False


def test_recent_returning_greeting_duplicate_blocks_rapid_resend():
    from backend.agents.chat.whatsapp_handler import _recent_returning_greeting_duplicate
    from datetime import datetime

    session = Session(session_id="t", phone_number="+1", channel="whatsapp")
    session.flow_state["returning_greeting_sent_at"] = datetime.utcnow().isoformat() + "Z"
    session.flow_state["last_returning_greeting_msg"] = "HII"
    assert _recent_returning_greeting_duplicate(
        session,
        norm_msg="HII",
        dedup_key="SM1",
    ) is True


@pytest.mark.asyncio
async def test_fetch_user_addresses_live():
    from backend.integrations.tatva_user_addresses import fetch_user_addresses

    addresses = await fetch_user_addresses("698045af7d79fe3c880dab0f", session_id="test")
    assert addresses
    assert any(a.get("formattedAddress") for a in addresses)

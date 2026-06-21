"""Tests for Tatva user address API integration."""
import pytest

from backend.integrations.tatva_user_addresses import (
    normalize_user_addresses,
    saved_addresses_display,
)
from backend.integrations.returning_user_flow import (
    returning_saved_location_step,
    parse_returning_location_choice,
    apply_returning_location_choice,
    RETURNING_LOCATION_FIELD,
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
    assert labels == ["Address 1", "Address 2", "Add new location"]
    values = [o["value"] for o in step["options"]]
    assert values[-1] == "add_new_location"
    assert "69d393184d8aa84fc60b95b1" in values


def test_parse_address_short_label_selection():
    session = Session(session_id="t", phone_number="+1", channel="whatsapp")
    session.flow_state["tatva_user_addresses"] = SAMPLE_ADDRESSES
    assert parse_returning_location_choice("Address 2", session=session) == "69ca149a76447fb2e241a65d"
    assert parse_returning_location_choice("2", session=session) == "69ca149a76447fb2e241a65d"


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
    assert "HSR Layout" in session.extracted_fields["property_location"]
    assert session.extracted_fields["city"] == "Bengaluru Urban"


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
async def test_fetch_user_addresses_live():
    from backend.integrations.tatva_user_addresses import fetch_user_addresses

    addresses = await fetch_user_addresses("698045af7d79fe3c880dab0f", session_id="test")
    assert addresses
    assert any(a.get("formattedAddress") for a in addresses)

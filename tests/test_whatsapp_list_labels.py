"""WhatsApp list-picker row title + description tests."""
from backend.agents.chat.twilio_client import (
    WHATSAPP_LIST_TITLE_MAX,
    _build_content_variables,
    _twilio_list_row,
    enrich_whatsapp_mcq_step,
)


def test_short_label_no_description():
    title, desc = _twilio_list_row("New Home Build")
    assert title == "New Home Build"
    assert desc == ""


def test_long_label_puts_full_text_in_description():
    long_label = "Floor Addition / Extension"
    title, desc = _twilio_list_row(long_label)
    assert len(title) <= WHATSAPP_LIST_TITLE_MAX
    assert desc == long_label


def test_build_content_variables_includes_descriptions(monkeypatch):
    monkeypatch.setattr(
        "backend.agents.chat.twilio_client.settings.twilio_whatsapp_quick_reply",
        True,
    )
    monkeypatch.setattr(
        "backend.agents.chat.twilio_client.settings.twilio_mcq_list_5_content_sid",
        "HXtest5row",
    )
    step = {
        "type": "mcq",
        "field": "service_q1",
        "prompt": "What type of project?",
        "options": [
            {"label": "New Home Build", "value": "new_home_build"},
            {"label": "Floor Addition / Extension", "value": "floor_addition_extension"},
            {"label": "Structural Repair / Retrofit", "value": "structural_repair_retrofit"},
            {"label": "Farmhouse / Villa Construction", "value": "farmhouse_villa_construction"},
            {"label": "Commercial", "value": "commercial"},
        ],
    }
    enriched = enrich_whatsapp_mcq_step(step)
    assert enriched.get("twilio_list_use_descriptions") is True
    variables = _build_content_variables(enriched, enriched["options"])
    assert variables["option_1_label"] == "New Home Build"
    assert variables["option_1_description"] == ""
    assert variables["option_2_description"] == "Floor Addition / Extension"
    assert len(variables["option_2_label"]) <= WHATSAPP_LIST_TITLE_MAX

"""WhatsApp list-picker row title + description tests."""
from backend.agents.chat.twilio_client import (
    WHATSAPP_LIST_TITLE_MAX,
    _build_content_variables,
    _compact_list_title,
    _twilio_list_row,
    enrich_whatsapp_mcq_step,
)


def test_short_label_includes_description():
    title, desc = _twilio_list_row("New Home Build")
    assert title == "New Home Build"
    assert desc == "New Home Build"


def test_long_label_puts_full_text_in_description():
    long_label = "Floor Addition / Extension"
    title, desc = _twilio_list_row(long_label)
    assert len(title) <= WHATSAPP_LIST_TITLE_MAX
    assert desc == long_label


def test_compact_title_prefers_parenthetical():
    assert _compact_list_title("Immediate (Within 24 Hours)") == "Within 24 Hours"
    assert _compact_list_title("Full Property (Interior + Exterior)") == "Interior + Exterior"


def test_compact_title_prefers_second_segment():
    assert _compact_list_title("Residential – Independent Home") == "Independent Home"
    title = _compact_list_title("Industrial / Manufacturing Plant")
    assert len(title) <= WHATSAPP_LIST_TITLE_MAX
    assert title == "Manufacturing Plant"


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
            {"label": "Home Build", "value": "new_home_build"},
            {"label": "Addition", "value": "addition"},
            {"label": "Repair", "value": "repair"},
            {"label": "Farmhouse", "value": "farmhouse"},
            {"label": "Commercial", "value": "commercial"},
        ],
    }
    enriched = enrich_whatsapp_mcq_step(step)
    assert enriched.get("twilio_list_use_descriptions") is True
    variables = _build_content_variables(enriched, enriched["options"])
    assert variables["option_1_label"] == "Home Build"
    assert variables["option_1_description"] == "Home Build"
    assert variables["option_2_description"] == "Addition"
    assert len(variables["option_2_label"]) <= WHATSAPP_LIST_TITLE_MAX


def test_long_labels_keep_interactive_mcq(monkeypatch):
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
    assert enriched.get("force_plain_mcq") is not True
    assert enriched.get("twilio_content_sid") == "HXtest5row"


def test_format_mcq_options_display_shows_all_options():
    from backend.agents.chat.twilio_client import format_mcq_options_display

    step = {
        "type": "mcq",
        "field": "order_1",
        "prompt": "What type of residential construction project are you planning?",
        "options": [
            {"label": "New Home Build", "value": "new_home_build"},
            {"label": "Floor Addition / Extension", "value": "floor_addition_extension"},
            {"label": "Structural Repair / Retrofit", "value": "structural_repair_retrofit"},
            {"label": "Farmhouse / Villa Construction", "value": "farmhouse_villa_construction"},
            {"label": "Commercial", "value": "commercial"},
        ],
    }
    text = format_mcq_options_display(step)
    assert "What type of residential construction project are you planning?" in text
    assert "1. New Home Build" in text
    assert "2. Floor Addition / Extension" in text
    assert "3. Structural Repair / Retrofit" in text
    assert "4. Farmhouse / Villa Construction" in text
    assert "5. Commercial" in text

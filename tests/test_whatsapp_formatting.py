"""WhatsApp summary text styling."""
from backend.utils.whatsapp_formatting import whatsapp_question_emphasis


def test_whatsapp_question_emphasis_uses_calligraphy_script():
    assert whatsapp_question_emphasis("What type") == "𝒲𝒽𝒶𝓉 𝓉𝓎𝓅ℯ"
    assert whatsapp_question_emphasis("budget ₹40") == "𝒷𝓊𝒹ℊℯ𝓉 ₹40"
    assert whatsapp_question_emphasis("a * b") == "𝒶  𝒷"

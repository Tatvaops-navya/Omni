"""WhatsApp summary text styling."""
from backend.utils.whatsapp_formatting import whatsapp_question_emphasis


def test_whatsapp_question_emphasis_italicizes_letters_only():
    assert whatsapp_question_emphasis("What type") == "𝘞𝘩𝘢𝘵 𝘵𝘺𝘱𝘦"
    assert whatsapp_question_emphasis("budget ₹40") == "𝘣𝘶𝘥𝘨𝘦𝘵 ₹40"

"""WhatsApp summary text styling."""
from backend.utils.whatsapp_formatting import whatsapp_question_emphasis


def test_whatsapp_question_emphasis_bolds_question_neatly():
    assert whatsapp_question_emphasis("What type") == "*What type*"
    assert whatsapp_question_emphasis("budget ₹40") == "*budget ₹40*"
    assert whatsapp_question_emphasis("a _ b") == "*a  b*"

"""WhatsApp message text styling helpers."""
from __future__ import annotations


def whatsapp_question_emphasis(text: str) -> str:
    """Clean bold labels for enquiry-summary questions (answers stay regular weight)."""
    clean = (text or "").strip().replace("*", "").replace("_", "")
    if not clean:
        return text or ""
    return f"*{clean}*"

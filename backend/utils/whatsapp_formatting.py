"""WhatsApp message text styling helpers."""
from __future__ import annotations

# Mathematical Sans-Serif Italic — elegant question emphasis (readable on WhatsApp).
_SANS_ITALIC_CAP_A = 0x1D608
_SANS_ITALIC_SMALL_A = 0x1D622


def whatsapp_question_emphasis(text: str) -> str:
    """Style enquiry-summary question labels (answers stay in normal text)."""
    if not text:
        return text
    styled: list[str] = []
    for ch in text:
        code = ord(ch)
        if 0x41 <= code <= 0x5A:
            styled.append(chr(_SANS_ITALIC_CAP_A + code - 0x41))
        elif 0x61 <= code <= 0x7A:
            styled.append(chr(_SANS_ITALIC_SMALL_A + code - 0x61))
        else:
            styled.append(ch)
    return "".join(styled)

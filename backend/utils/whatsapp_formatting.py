"""WhatsApp message text styling helpers."""
from __future__ import annotations

# Mathematical Script — formal calligraphy-style letters (WhatsApp-safe; no custom fonts).
_SCRIPT_CAPITALS = str.maketrans(
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ",
    "𝒜ℬ𝒞𝒟ℰℱ𝒢ℋℐ𝒥𝒦ℒℳ𝒩𝒪𝒫𝒬ℛ𝒮𝒯𝒰𝒱𝒲𝒳𝒴𝒵",
)
_SCRIPT_SMALL = str.maketrans(
    "abcdefghijklmnopqrstuvwxyz",
    "𝒶𝒷𝒸𝒹ℯ𝒻ℊ𝒽𝒾𝒿𝓀𝓁𝓂𝓃ℴ𝓅𝓆𝓇𝓈𝓉𝓊𝓋𝓌𝓍𝓎𝓏",
)


def whatsapp_question_emphasis(text: str) -> str:
    """Calligraphy-style script for enquiry-summary questions (answers stay normal)."""
    clean = (text or "").strip().replace("*", "")
    if not clean:
        return text or ""
    return clean.translate(_SCRIPT_CAPITALS).translate(_SCRIPT_SMALL)

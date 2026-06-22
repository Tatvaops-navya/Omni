"""
Parse Twilio WhatsApp interactive inbound fields (list picker, buttons).
"""
from __future__ import annotations

import json
import re
from typing import Any

# WhatsApp appends this footer on quoted list/button replies (not from our bot text).
_INTERACTIVE_REPLY_FOOTERS = frozenset({
    "tap to select",
    "tap to choose",
    "toque para selecionar",
    "toca para seleccionar",
})


def sanitize_whatsapp_inbound_text(text: str) -> str:
    """Remove WhatsApp interactive reply footers like *Tap to select*."""
    raw = (text or "").strip()
    if not raw:
        return ""
    lines = [ln.strip() for ln in raw.replace("\r", "\n").split("\n")]
    kept: list[str] = []
    for ln in lines:
        lower = ln.lower()
        if lower in _INTERACTIVE_REPLY_FOOTERS:
            continue
        if re.match(r"^tap to (select|choose)\b", lower):
            continue
        kept.append(ln)
    return "\n".join(kept).strip() if kept else raw


def build_inbound_user_message(
    *,
    body: str = "",
    button_text: str = "",
    list_title: str = "",
    list_id: str = "",
    button_payload: str = "",
    interactive_data: str = "",
) -> str:
    """
    Build the user text for flow logic.
    For list/button taps, prefer ListTitle/ButtonText (clean label) over Body
    (Body often includes *Tap to select* from WhatsApp's quoted reply UI).
    """
    resolved_id = parse_list_selection_id(
        list_id=list_id,
        button_payload=button_payload,
        interactive_data=interactive_data,
    )
    is_interactive = bool(resolved_id or list_id or button_payload or button_text)

    if is_interactive:
        for candidate in (list_title, button_text):
            cleaned = sanitize_whatsapp_inbound_text(candidate)
            if cleaned:
                return cleaned
        cleaned_body = sanitize_whatsapp_inbound_text(body)
        if cleaned_body:
            # Quoted list replies often embed the full prior bot message (e.g. EVA welcome).
            lines = [ln.strip() for ln in cleaned_body.replace("\r", "\n").split("\n") if ln.strip()]
            if len(lines) > 1:
                for line in reversed(lines):
                    lower = line.lower()
                    if lower.startswith("address") or lower in {
                        "other address",
                        "add new location",
                        "other",
                    }:
                        return line
                return lines[-1]
            return cleaned_body
        return ""

    return sanitize_whatsapp_inbound_text(body or button_text or list_title or "")


def _dig_id(obj: Any) -> str:
    if not isinstance(obj, dict):
        return ""
    for key in ("id", "payload", "postback_data", "selected_id", "list_id"):
        val = obj.get(key)
        if val is not None and str(val).strip():
            return str(val).strip()
    return ""


def parse_list_selection_id(
    *,
    list_id: str = "",
    button_payload: str = "",
    interactive_data: str = "",
) -> str:
    """
    Return the list row id from Twilio inbound params.
    List pickers may send the id only inside InteractiveData JSON.
    """
    for candidate in (list_id, button_payload):
        if candidate and candidate.strip():
            return candidate.strip()

    raw = (interactive_data or "").strip()
    if not raw:
        return ""

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return ""

    if isinstance(data, str):
        return data.strip()

    if not isinstance(data, dict):
        return ""

    direct = _dig_id(data)
    if direct:
        return direct

    for key in (
        "list_reply",
        "listPickerReply",
        "list_picker_reply",
        "list_response",
        "listResponse",
        "button_reply",
    ):
        nested = data.get(key)
        found = _dig_id(nested)
        if found:
            return found

    channel = data.get("channel") or data.get("channelMetadata")
    if isinstance(channel, dict):
        found = _dig_id(channel)
        if found:
            return found
        inner = channel.get("interactiveData") or channel.get("interactive")
        if isinstance(inner, dict):
            found = _dig_id(inner)
            if found:
                return found

    return ""

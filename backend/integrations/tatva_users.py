"""
Tatva user registration via withtatva.ai API.
"""
from __future__ import annotations

import re
from typing import Any, Optional

import httpx

from backend.config import get_settings
from backend.schemas.session import Session
from backend.utils.logger import log_event

REGISTER_PHONE_PATH = "/users/api/users/register-phone"


def normalize_phone_for_tatva(phone: str) -> str:
    """Strip WhatsApp/E.164 prefixes and return a 10-digit Indian mobile number."""
    raw = (phone or "").strip()
    if raw.lower().startswith("whatsapp:"):
        raw = raw.split(":", 1)[-1]
    digits = re.sub(r"\D", "", raw)
    if digits.startswith("91") and len(digits) >= 12:
        digits = digits[2:]
    if len(digits) > 10:
        digits = digits[-10:]
    return digits


def _extract_user_id(payload: dict[str, Any]) -> Optional[str]:
    data = payload.get("data") or {}
    user = data.get("user") or {}
    user_id = user.get("_id")
    return str(user_id) if user_id else None


async def register_phone_user(
    phone_number: str,
    *,
    session_id: str = "unknown",
) -> Optional[dict[str, Any]]:
    """Register or look up a user by phone. Returns API JSON on success, else None."""
    settings = get_settings()
    normalized = normalize_phone_for_tatva(phone_number)
    if not normalized:
        await log_event(
            "API_ERROR",
            session_id=session_id,
            data={"api": "tatva_register_phone", "error": "invalid_phone", "phone": phone_number},
        )
        return None

    base_url = (settings.tatva_users_api_base_url or "").rstrip("/")
    if not base_url:
        await log_event(
            "API_ERROR",
            session_id=session_id,
            data={"api": "tatva_register_phone", "error": "api_not_configured"},
        )
        return None

    url = f"{base_url}{REGISTER_PHONE_PATH}"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(url, json={"phoneNumber": normalized})
            response.raise_for_status()
            payload = response.json()
    except Exception as exc:
        await log_event(
            "API_ERROR",
            session_id=session_id,
            data={
                "api": "tatva_register_phone",
                "error": str(exc),
                "phone": normalized,
            },
        )
        return None

    if not payload.get("success"):
        await log_event(
            "API_ERROR",
            session_id=session_id,
            data={
                "api": "tatva_register_phone",
                "error": payload.get("message") or "unsuccessful_response",
                "phone": normalized,
            },
        )
        return None

    return payload


async def register_tatva_user_for_session(session: Session) -> None:
    """Call register-phone and persist Tatva user _id on the session."""
    if session.extracted_fields.get("tatva_user_id"):
        return

    phone = (
        session.extracted_fields.get("phone_number")
        or session.phone_number
        or ""
    )
    payload = await register_phone_user(phone, session_id=session.session_id)
    if not payload:
        return

    user_id = _extract_user_id(payload)
    if not user_id:
        await log_event(
            "API_ERROR",
            session_id=session.session_id,
            data={"api": "tatva_register_phone", "error": "missing_user_id"},
        )
        return

    session.extracted_fields["tatva_user_id"] = user_id
    session.flow_state["tatva_user_registered"] = True
    if "tatva_user_id" not in session.completed_fields:
        session.completed_fields.append("tatva_user_id")

    await log_event(
        "TATVA_USER_REGISTERED",
        session_id=session.session_id,
        data={
            "tatva_user_id": user_id,
            "created": (payload.get("data") or {}).get("created"),
            "message": payload.get("message"),
        },
    )

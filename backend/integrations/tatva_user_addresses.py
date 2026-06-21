"""
Fetch saved Tatva user addresses for returning-user location selection.
GET /users/api/address/user/{userId}
"""
from __future__ import annotations

from typing import Any, Optional

import httpx

from backend.config import get_settings
from backend.integrations.tatva_users import TATVA_HTTP_HEADERS
from backend.intelligence import stage_engine as se
from backend.schemas.session import Session
from backend.utils.logger import log_event

USER_ADDRESSES_PATH = "/users/api/address/user"


def _build_formatted_address(addr: dict[str, Any]) -> str:
    formatted = str(addr.get("formattedAddress") or "").strip()
    if formatted:
        return formatted
    parts = [
        str(addr.get("building") or "").strip(),
        str(addr.get("buildingName") or "").strip(),
        str(addr.get("street") or "").strip(),
        str(addr.get("locality") or "").strip(),
        str(addr.get("district") or "").strip(),
        str(addr.get("state") or "").strip(),
        str(addr.get("zip") or "").strip(),
    ]
    return ", ".join(p for p in parts if p)


def normalize_user_addresses(addresses: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Dedupe by formatted address; default address first."""
    seen: dict[str, dict[str, Any]] = {}
    for addr in addresses:
        if not isinstance(addr, dict):
            continue
        key = _build_formatted_address(addr).lower()
        if not key:
            key = str(addr.get("_id") or "")
        existing = seen.get(key)
        if not existing or addr.get("isDefault"):
            seen[key] = addr
    result = list(seen.values())
    defaults = [a for a in result if a.get("isDefault")]
    others = [a for a in result if not a.get("isDefault")]
    defaults.sort(key=lambda a: str(a.get("updatedAt") or ""), reverse=True)
    others.sort(key=lambda a: str(a.get("updatedAt") or ""), reverse=True)
    return defaults + others


def format_address_display_line(addr: dict[str, Any], *, index: int | None = None) -> str:
    text = _build_formatted_address(addr)
    prefix = f"{index}. " if index is not None else "📍 "
    suffix = " (Default)" if addr.get("isDefault") else ""
    label = str(addr.get("subTypeLabel") or "").strip()
    if label:
        return f"{prefix}{label}: {text}{suffix}"
    return f"{prefix}{text}{suffix}"


def address_list_label(addr: dict[str, Any]) -> str:
    """Short label for WhatsApp list row."""
    label = str(addr.get("subTypeLabel") or "").strip()
    locality = str(addr.get("locality") or addr.get("district") or "").strip()
    if label and locality:
        return f"{label} - {locality}"
    if locality:
        return locality
    formatted = _build_formatted_address(addr)
    return formatted[:40] + ("…" if len(formatted) > 40 else "")


def profile_fields_from_address(addr: dict[str, Any]) -> dict[str, str]:
    city = str(addr.get("district") or addr.get("locality") or "").strip()
    prop = _build_formatted_address(addr)
    return {"city": city or prop.split(",")[0].strip(), "property_location": prop}


async def fetch_user_addresses(
    user_id: str,
    *,
    session_id: str = "unknown",
) -> list[dict[str, Any]]:
    settings = get_settings()
    base_url = (settings.tatva_users_api_base_url or "").rstrip("/")
    uid = str(user_id or "").strip()
    if not base_url or not uid:
        return []

    url = f"{base_url}{USER_ADDRESSES_PATH}/{uid}"
    await log_event(
        "TATVA_USER_ADDRESSES_FETCH",
        session_id=session_id,
        data={"api": "tatva_user_addresses", "url": url, "user_id": uid},
    )
    try:
        async with httpx.AsyncClient(timeout=10.0, headers=TATVA_HTTP_HEADERS) as client:
            response = await client.get(url)
            response.raise_for_status()
            payload = response.json()
    except Exception as exc:
        await log_event(
            "API_ERROR",
            session_id=session_id,
            data={"api": "tatva_user_addresses", "error": str(exc), "user_id": uid},
        )
        return []

    if not payload.get("success"):
        return []

    data = payload.get("data")
    if not isinstance(data, list):
        return []

    await log_event(
        "TATVA_USER_ADDRESSES_OK",
        session_id=session_id,
        data={"user_id": uid, "count": len(data)},
    )
    return [a for a in data if isinstance(a, dict)]


async def load_user_addresses_for_session(session: Session, *, force: bool = False) -> list[dict[str, Any]]:
    """Fetch Tatva addresses and cache on session.flow_state."""
    user_id = str(session.extracted_fields.get("tatva_user_id") or "").strip()
    if not user_id:
        session.flow_state.pop("tatva_user_addresses", None)
        return []

    if not force and session.flow_state.get("tatva_user_addresses") is not None:
        cached = session.flow_state.get("tatva_user_addresses")
        return list(cached) if isinstance(cached, list) else []

    raw = await fetch_user_addresses(user_id, session_id=session.session_id)
    normalized = normalize_user_addresses(raw)
    session.flow_state["tatva_user_addresses"] = normalized
    return normalized


def get_cached_user_addresses(session: Session) -> list[dict[str, Any]]:
    cached = session.flow_state.get("tatva_user_addresses")
    if isinstance(cached, list):
        return cached
    return []


def is_tatva_address_id(value: str, session: Session) -> bool:
    needle = str(value or "").strip()
    if not needle:
        return False
    return any(str(addr.get("_id") or "") == needle for addr in get_cached_user_addresses(session))


def apply_tatva_address_to_session(session: Session, address_id: str) -> bool:
    """Apply a selected Tatva address to city / property_location."""
    needle = str(address_id or "").strip()
    for addr in get_cached_user_addresses(session):
        if str(addr.get("_id") or "") != needle:
            continue
        fields = profile_fields_from_address(addr)
        se.mark_field_validated(session, "city", fields["city"])
        se.mark_field_validated(session, "property_location", fields["property_location"])
        session.flow_state["selected_tatva_address_id"] = needle
        return True
    return False


def saved_addresses_display(session: Session) -> str:
    """Multi-line display of all Tatva saved addresses."""
    addresses = get_cached_user_addresses(session)
    if not addresses:
        return ""
    return "\n".join(format_address_display_line(addr, index=i + 1) for i, addr in enumerate(addresses))

"""Tatva meet-link schedules for CRM admin panel Users page."""
from __future__ import annotations

from typing import Any

import httpx

from backend.config import get_settings
from backend.integrations.tatva_users import TATVA_HTTP_HEADERS, normalize_phone_for_tatva

MEET_LINKS_PATH = "/users/api/meet-links/all"


def _tatva_admin_headers() -> dict[str, str]:
    headers = {
        **TATVA_HTTP_HEADERS,
        "Content-Type": "application/json",
    }
    api_key = (get_settings().admin_api_key or "").strip()
    if api_key and api_key != "changeme":
        headers["X-Admin-Key"] = api_key
    return headers


def _user_id_from_item(item: dict[str, Any]) -> str:
    user = item.get("userId")
    if isinstance(user, dict):
        return str(user.get("_id") or "").strip()
    return str(item.get("userId") or "").strip()


def _phone_from_item(item: dict[str, Any]) -> str:
    user = item.get("userId")
    if isinstance(user, dict):
        return normalize_phone_for_tatva(str(user.get("phoneNumber") or ""))
    return ""


def _matches_user(
    item: dict[str, Any],
    *,
    user_id: str | None,
    phone: str | None,
) -> bool:
    if user_id and _user_id_from_item(item) == user_id.strip():
        return True
    if phone:
        needle = normalize_phone_for_tatva(phone)
        if needle and _phone_from_item(item) == needle:
            return True
    return not user_id and not phone


async def fetch_meet_links(
    *,
    page: int = 1,
    limit: int = 20,
    user_id: str | None = None,
    phone: str | None = None,
) -> dict[str, Any]:
    """GET meet-link schedules from Tatva; optionally filter to one user."""
    settings = get_settings()
    base_url = (settings.tatva_users_api_base_url or "").rstrip("/")
    if not base_url:
        return {
            "success": False,
            "message": "Tatva API not configured",
            "data": [],
            "pagination": {"page": page, "limit": limit, "total": 0, "totalPages": 0},
        }

    params = {"page": max(1, page), "limit": max(1, min(limit, 100))}
    if user_id or phone:
        params["limit"] = 100
        params["page"] = 1
    url = f"{base_url}{MEET_LINKS_PATH}"
    try:
        async with httpx.AsyncClient(timeout=30.0, headers=_tatva_admin_headers()) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            payload = response.json()
    except httpx.HTTPStatusError as exc:
        return {
            "success": False,
            "message": str(exc),
            "data": [],
            "pagination": {"page": page, "limit": limit, "total": 0, "totalPages": 0},
            "error_status": exc.response.status_code,
        }
    except Exception as exc:
        return {
            "success": False,
            "message": str(exc),
            "data": [],
            "pagination": {"page": page, "limit": limit, "total": 0, "totalPages": 0},
        }

    if not isinstance(payload, dict):
        return {
            "success": False,
            "message": "Invalid response from Tatva meet-links API",
            "data": [],
            "pagination": {"page": page, "limit": limit, "total": 0, "totalPages": 0},
        }

    items = payload.get("data") if isinstance(payload.get("data"), list) else []
    if user_id or phone:
        items = [item for item in items if isinstance(item, dict) and _matches_user(item, user_id=user_id, phone=phone)]

    pagination = payload.get("pagination") if isinstance(payload.get("pagination"), dict) else {}
    return {
        "success": bool(payload.get("success", True)),
        "message": str(payload.get("message") or ""),
        "data": items,
        "pagination": {
            "page": int(pagination.get("page") or page),
            "limit": int(pagination.get("limit") or limit),
            "total": int(pagination.get("total") or len(items)),
            "totalPages": int(pagination.get("totalPages") or 1),
        },
    }

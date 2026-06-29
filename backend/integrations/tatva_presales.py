"""
Submit presales lead after the create-project Yes/No step.
POST /admin/api/admin/presales
"""
from __future__ import annotations

from typing import Any

import httpx

from backend.config import get_settings
from backend.integrations.returning_user_flow import resolve_returning_client_name
from backend.integrations.tatva_users import TATVA_HTTP_HEADERS, normalize_phone_for_tatva
from backend.schemas.session import Session
from backend.utils.logger import log_event

PRESALES_PATH = "/admin/api/admin/presales"
PRESALES_FLAG_HIGH = "high"
PRESALES_FLAG_LOW = "low"


def presales_flag_for_project_choice(value: Any) -> str:
    """Map willing_to_create_project answer to Tatva presales flag."""
    choice = str(value or "").strip().lower()
    if choice in ("no", "n"):
        return PRESALES_FLAG_LOW
    return PRESALES_FLAG_HIGH


def build_presales_payload(session: Session, *, flag: str) -> dict[str, str]:
    """Map session profile fields to Tatva presales API body."""
    phone = normalize_phone_for_tatva(
        str(session.extracted_fields.get("phone_number") or session.phone_number or "")
    )
    name = resolve_returning_client_name(session) or str(
        session.extracted_fields.get("client_name") or ""
    ).strip()
    email = str(session.extracted_fields.get("email") or "").strip()
    location = str(session.extracted_fields.get("city") or "").strip()
    property_location = str(session.extracted_fields.get("property_location") or "").strip()
    return {
        "name": name,
        "email": email,
        "phoneNumber": phone,
        "location": location,
        "propertyLocation": property_location,
        "flag": flag,
    }


def _presales_headers() -> dict[str, str]:
    headers = {
        **TATVA_HTTP_HEADERS,
        "Content-Type": "application/json",
    }
    api_key = (get_settings().admin_api_key or "").strip()
    if api_key and api_key != "changeme":
        headers["X-Admin-Key"] = api_key
    return headers


async def submit_presales_lead(session: Session, *, flag: str) -> bool:
    """
    POST presales lead after willing_to_create_project is answered.
    Idempotent per session ΓÇö skips if already submitted.
    """
    if session.flow_state.get("tatva_presales_submitted"):
        return True

    body = build_presales_payload(session, flag=flag)
    if not body.get("phoneNumber"):
        await log_event(
            "API_ERROR",
            session_id=session.session_id,
            data={"api": "tatva_presales", "error": "missing_phone_number"},
        )
        return False

    settings = get_settings()
    base_url = (settings.tatva_users_api_base_url or "").rstrip("/")
    if not base_url:
        await log_event(
            "API_ERROR",
            session_id=session.session_id,
            data={"api": "tatva_presales", "error": "api_not_configured"},
        )
        return False

    url = f"{base_url}{PRESALES_PATH}"
    await log_event(
        "TATVA_PRESALES_SUBMIT",
        session_id=session.session_id,
        data={
            "api": "tatva_presales",
            "url": url,
            "phone": body.get("phoneNumber"),
            "flag": flag,
            "has_name": bool(body.get("name")),
            "has_email": bool(body.get("email")),
        },
    )

    try:
        async with httpx.AsyncClient(timeout=30.0, headers=_presales_headers()) as client:
            response = await client.post(url, json=body)
            response.raise_for_status()
            payload = response.json()
    except httpx.HTTPStatusError as exc:
        await log_event(
            "API_ERROR",
            session_id=session.session_id,
            data={
                "api": "tatva_presales",
                "error": str(exc),
                "status_code": exc.response.status_code,
                "url": url,
                "response_body": (exc.response.text or "")[:500],
            },
        )
        return False
    except Exception as exc:
        await log_event(
            "API_ERROR",
            session_id=session.session_id,
            data={
                "api": "tatva_presales",
                "error": str(exc),
                "error_type": type(exc).__name__,
                "url": url,
            },
        )
        return False

    if payload.get("success") is False:
        await log_event(
            "API_ERROR",
            session_id=session.session_id,
            data={
                "api": "tatva_presales",
                "error": payload.get("message") or "unsuccessful_response",
                "url": url,
            },
        )
        return False

    session.flow_state["tatva_presales_submitted"] = True
    await log_event(
        "TATVA_PRESALES_SUBMIT_OK",
        session_id=session.session_id,
        data={
            "api": "tatva_presales",
            "phone": body.get("phoneNumber"),
            "flag": flag,
            "message": payload.get("message"),
        },
    )
    return True


async def submit_presales_on_project_decline(session: Session) -> bool:
    """Backward-compatible wrapper for decline-only callers."""
    if not session.flow_state.get("project_declined"):
        return False
    return await submit_presales_lead(session, flag=PRESALES_FLAG_LOW)


async def fetch_presales_records(
    *,
    page: int = 1,
    limit: int = 20,
    flag: str | None = None,
) -> dict[str, Any]:
    """GET presales list from Tatva admin API for Krsna admin panel."""
    settings = get_settings()
    base_url = (settings.tatva_users_api_base_url or "").rstrip("/")
    if not base_url:
        return {
            "success": False,
            "message": "Tatva API not configured",
            "data": {"items": [], "total": 0, "page": page, "limit": limit, "totalPages": 0},
        }

    params: dict[str, str | int] = {"page": max(1, page), "limit": max(1, min(limit, 100))}
    if flag and flag.strip().lower() in (PRESALES_FLAG_HIGH, PRESALES_FLAG_LOW):
        params["flag"] = flag.strip().lower()

    url = f"{base_url}{PRESALES_PATH}"
    try:
        async with httpx.AsyncClient(timeout=30.0, headers=_presales_headers()) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            payload = response.json()
    except httpx.HTTPStatusError as exc:
        return {
            "success": False,
            "message": str(exc),
            "data": {
                "items": [],
                "total": 0,
                "page": page,
                "limit": limit,
                "totalPages": 0,
                "error_status": exc.response.status_code,
            },
        }
    except Exception as exc:
        return {
            "success": False,
            "message": str(exc),
            "data": {"items": [], "total": 0, "page": page, "limit": limit, "totalPages": 0},
        }

    if not isinstance(payload, dict):
        return {
            "success": False,
            "message": "Invalid response from Tatva presales API",
            "data": {"items": [], "total": 0, "page": page, "limit": limit, "totalPages": 0},
        }

    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    items = data.get("items") if isinstance(data.get("items"), list) else []
    return {
        "success": bool(payload.get("success", True)),
        "message": str(payload.get("message") or ""),
        "data": {
            "items": items,
            "total": int(data.get("total") or len(items)),
            "page": int(data.get("page") or page),
            "limit": int(data.get("limit") or limit),
            "totalPages": int(data.get("totalPages") or 1),
        },
    }


async def delete_presales_record(presales_id: str) -> dict[str, Any]:
    """DELETE presales lead from Tatva admin API."""
    record_id = (presales_id or "").strip()
    if not record_id:
        return {"success": False, "message": "Missing presales id"}

    settings = get_settings()
    base_url = (settings.tatva_users_api_base_url or "").rstrip("/")
    if not base_url:
        return {"success": False, "message": "Tatva API not configured"}

    url = f"{base_url}{PRESALES_PATH}/{record_id}"
    try:
        async with httpx.AsyncClient(timeout=30.0, headers=_presales_headers()) as client:
            response = await client.delete(url)
            response.raise_for_status()
            payload = response.json() if response.content else {}
    except httpx.HTTPStatusError as exc:
        return {
            "success": False,
            "message": str(exc),
            "error_status": exc.response.status_code,
        }
    except Exception as exc:
        return {"success": False, "message": str(exc)}

    if isinstance(payload, dict) and payload.get("success") is False:
        return {
            "success": False,
            "message": str(payload.get("message") or "Delete failed"),
        }
    return {
        "success": True,
        "message": str((payload or {}).get("message") or "Deleted"),
    }

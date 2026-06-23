"""
Submit presales lead when a user declines project creation.
POST /admin/api/admin/presales
"""
from __future__ import annotations

from typing import Any, Optional

import httpx

from backend.config import get_settings
from backend.integrations.returning_user_flow import resolve_returning_client_name
from backend.integrations.tatva_users import TATVA_HTTP_HEADERS, normalize_phone_for_tatva
from backend.intelligence import stage_engine as se
from backend.schemas.session import Session
from backend.utils.logger import log_event

PRESALES_PATH = "/admin/api/admin/presales"


def build_presales_payload(session: Session) -> dict[str, str]:
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


async def submit_presales_on_project_decline(session: Session) -> bool:
    """
    POST presales lead when willing_to_create_project is No.
    Idempotent per session — skips if already submitted.
    """
    if not session.flow_state.get("project_declined"):
        return False
    if session.flow_state.get("tatva_presales_submitted"):
        return True

    body = build_presales_payload(session)
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
    se.mark_field_validated(session, "willing_to_create_project", "no")
    await log_event(
        "TATVA_PRESALES_SUBMIT_OK",
        session_id=session.session_id,
        data={
            "api": "tatva_presales",
            "phone": body.get("phoneNumber"),
            "message": payload.get("message"),
        },
    )
    return True

"""
Tatva user registration via withtatva.ai API.
"""
from __future__ import annotations

import re
from typing import Any, Optional

import httpx

from backend.config import get_settings
from backend.intelligence import stage_engine as se
from backend.schemas.session import Session
from backend.utils.logger import log_event

CHECK_PHONE_PATH = "/users/api/users/check-phone"
REGISTER_PHONE_PATH = "/users/api/users/register-phone"
LIST_USERS_PATH = "/users/api/users"
TATVA_HTTP_HEADERS = {"User-Agent": "TatvaOps-Omni/1.0", "Accept": "application/json"}

VENDOR_BLOCKED_MESSAGE = (
    "Sorry, this phone number is already registered as a TatvaOps vendor.\n\n"
    "Please connect with us using a different mobile number to submit a customer enquiry.\n\n"
    "Thank you for your understanding."
)


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


def _session_phone(session: Session) -> str:
    return str(
        session.extracted_fields.get("phone_number")
        or session.phone_number
        or ""
    )


def _extract_user_id(payload: dict[str, Any]) -> Optional[str]:
    data = payload.get("data") or {}
    user = data.get("user") or {}
    user_id = user.get("_id")
    return str(user_id) if user_id else None


def is_vendor_response(payload: dict[str, Any]) -> bool:
    return bool((payload.get("data") or {}).get("isVendor"))


def is_unregistered_phone_response(payload: dict[str, Any]) -> bool:
    data = payload.get("data") or {}
    return (
        not data.get("isUser")
        and not data.get("isVendor")
        and not data.get("user")
    )


def _name_from_user(user: dict[str, Any]) -> str:
    direct = (
        user.get("fullName")
        or user.get("full_name")
        or user.get("name")
        or user.get("displayName")
        or user.get("userName")
        or ""
    )
    if str(direct).strip():
        return str(direct).strip()
    first = str(user.get("firstName") or user.get("first_name") or "").strip()
    last = str(user.get("lastName") or user.get("last_name") or "").strip()
    if first or last:
        return " ".join(part for part in (first, last) if part)
    profile = user.get("profile")
    if isinstance(profile, dict):
        nested = (
            profile.get("fullName")
            or profile.get("full_name")
            or profile.get("name")
            or ""
        )
        if str(nested).strip():
            return str(nested).strip()
    return ""


def _location_from_user(user: dict[str, Any]) -> tuple[str, str]:
    city = str(user.get("city") or user.get("location") or "").strip()
    prop = str(
        user.get("propertyLocation")
        or user.get("property_location")
        or ""
    ).strip()
    address = user.get("address")
    if isinstance(address, str) and address.strip():
        if not prop:
            prop = address.strip()
    elif isinstance(address, dict):
        city = city or str(address.get("city") or "").strip()
        prop = prop or str(
            address.get("propertyLocation")
            or address.get("property_location")
            or address.get("line1")
            or address.get("address")
            or ""
        ).strip()
    return city, prop


def _apply_profile_fields(
    session: Session,
    *,
    name: str = "",
    email: str = "",
    city: str = "",
    property_location: str = "",
    force: bool = False,
) -> None:
    from backend.integrations.returning_user_flow import is_placeholder_client_name

    existing_name = str(session.extracted_fields.get("client_name") or "").strip()
    if name and (force or not existing_name or is_placeholder_client_name(existing_name)):
        se.mark_field_validated(session, "client_name", name)

    existing_email = str(session.extracted_fields.get("email") or "").strip()
    email_missing = not existing_email or existing_email.lower() in {"skipped", "skip"}
    if email and (force or email_missing):
        if se.is_valid_email_address(email):
            se.mark_field_validated(session, "email", email)
        else:
            session.extracted_fields["email"] = email
            if "email" not in session.completed_fields:
                session.completed_fields.append("email")

    if city and (force or not session.extracted_fields.get("city")):
        se.mark_field_validated(session, "city", city)
    if property_location and (force or not session.extracted_fields.get("property_location")):
        se.mark_field_validated(session, "property_location", property_location)


def _hydrate_profile_from_user(session: Session, user: dict[str, Any], *, force: bool = False) -> None:
    user_id = user.get("_id")
    if user_id and not session.extracted_fields.get("tatva_user_id"):
        session.extracted_fields["tatva_user_id"] = str(user_id)
        if "tatva_user_id" not in session.completed_fields:
            session.completed_fields.append("tatva_user_id")

    city, prop = _location_from_user(user)
    _apply_profile_fields(
        session,
        name=_name_from_user(user),
        email=str(user.get("email") or "").strip(),
        city=city,
        property_location=prop,
        force=force,
    )


async def hydrate_returning_user_profile(session: Session, *, force: bool = False) -> None:
    """Load returning-user profile and addresses from Tatva PM API only."""
    from backend.integrations.returning_user_flow import resolve_returning_client_name

    existing_name = resolve_returning_client_name(session)
    if (
        not force
        and existing_name
        and session.extracted_fields.get("tatva_user_id")
        and (
            session.extracted_fields.get("city")
            or session.extracted_fields.get("property_location")
        )
    ):
        return

    phone = _session_phone(session)
    payload = await check_phone_user(phone, session_id=session.session_id)
    if payload:
        data = payload.get("data") or {}
        if data.get("isUser"):
            session.flow_state["tatva_phone_checked"] = True
            session.flow_state["tatva_phone_is_user"] = True
            session.flow_state["tatva_user_registered"] = True
            user = data.get("user") or {}
            _hydrate_profile_from_user(session, user, force=force)

    if not resolve_returning_client_name(session) and session.flow_state.get("tatva_user_registered"):
        lookup = await register_phone_user(phone, session_id=session.session_id)
        if lookup:
            lookup_user = (lookup.get("data") or {}).get("user") or {}
            if lookup_user:
                _hydrate_profile_from_user(session, lookup_user, force=force)

    if session.extracted_fields.get("tatva_user_id"):
        from backend.integrations.tatva_user_addresses import load_user_addresses_for_session

        await load_user_addresses_for_session(session)


async def check_phone_user(
    phone_number: str,
    *,
    session_id: str = "unknown",
) -> Optional[dict[str, Any]]:
    """Check whether a phone belongs to an existing Tatva user or vendor."""
    settings = get_settings()
    normalized = normalize_phone_for_tatva(phone_number)
    if not normalized:
        await log_event(
            "API_ERROR",
            session_id=session_id,
            data={"api": "tatva_check_phone", "error": "invalid_phone", "phone": phone_number},
        )
        return None

    base_url = (settings.tatva_users_api_base_url or "").rstrip("/")
    if not base_url:
        await log_event(
            "API_ERROR",
            session_id=session_id,
            data={"api": "tatva_check_phone", "error": "api_not_configured"},
        )
        return None

    url = f"{base_url}{CHECK_PHONE_PATH}"
    await log_event(
        "TATVA_CHECK_PHONE",
        session_id=session_id,
        data={"api": "tatva_check_phone", "url": url, "phone": normalized},
    )
    try:
        async with httpx.AsyncClient(timeout=10.0, headers=TATVA_HTTP_HEADERS) as client:
            response = await client.post(url, json={"phoneNumber": normalized})
            response.raise_for_status()
            payload = response.json()
    except Exception as exc:
        await log_event(
            "API_ERROR",
            session_id=session_id,
            data={
                "api": "tatva_check_phone",
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
                "api": "tatva_check_phone",
                "error": payload.get("message") or "unsuccessful_response",
                "phone": normalized,
            },
        )
        return None

    await log_event(
        "TATVA_CHECK_PHONE_OK",
        session_id=session_id,
        data={
            "api": "tatva_check_phone",
            "phone": normalized,
            "is_user": (payload.get("data") or {}).get("isUser"),
            "is_vendor": (payload.get("data") or {}).get("isVendor"),
            "message": payload.get("message"),
        },
    )
    return payload


async def register_phone_user(
    phone_number: str,
    *,
    full_name: str | None = None,
    email: str | None = None,
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

    body: dict[str, str] = {"phoneNumber": normalized}
    if full_name and str(full_name).strip():
        body["fullName"] = str(full_name).strip()
    if email and str(email).strip():
        body["email"] = str(email).strip()

    url = f"{base_url}{REGISTER_PHONE_PATH}"
    await log_event(
        "TATVA_REGISTER_PHONE",
        session_id=session_id,
        data={
            "api": "tatva_register_phone",
            "url": url,
            "phone": normalized,
            "has_full_name": bool(body.get("fullName")),
            "has_email": bool(body.get("email")),
        },
    )
    try:
        async with httpx.AsyncClient(timeout=10.0, headers=TATVA_HTTP_HEADERS) as client:
            response = await client.post(url, json=body)
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


async def check_tatva_phone_for_session(session: Session) -> Optional[str]:
    """
    Call check-phone once per session on first contact.
    Returns VENDOR_BLOCKED_MESSAGE when isVendor is true.
    """
    if session.flow_state.get("vendor_blocked"):
        return VENDOR_BLOCKED_MESSAGE

    if session.flow_state.get("tatva_phone_checked"):
        return VENDOR_BLOCKED_MESSAGE if session.flow_state.get("vendor_blocked") else None

    session.flow_state["tatva_phone_checked"] = True

    phone = _session_phone(session)
    payload = await check_phone_user(phone, session_id=session.session_id)
    if not payload:
        return None

    data = payload.get("data") or {}
    session.flow_state["tatva_phone_check_data"] = data

    if is_vendor_response(payload):
        session.flow_state["vendor_blocked"] = True
        session.flow_state["conversation_ended"] = True
        await log_event(
            "TATVA_VENDOR_BLOCKED",
            session_id=session.session_id,
            data={
                "phone": normalize_phone_for_tatva(phone),
                "message": payload.get("message"),
                "source": "check_phone",
            },
        )
        return VENDOR_BLOCKED_MESSAGE

    is_user = bool(data.get("isUser"))
    session.flow_state["tatva_phone_is_user"] = is_user

    if is_user:
        user = data.get("user") or {}
        _hydrate_profile_from_user(session, user)
        session.flow_state["tatva_user_registered"] = True
        session.flow_state["tatva_needs_registration"] = False
        await log_event(
            "TATVA_USER_FOUND",
            session_id=session.session_id,
            data={
                "tatva_user_id": session.extracted_fields.get("tatva_user_id"),
                "message": payload.get("message"),
            },
        )
        return None

    if is_unregistered_phone_response(payload):
        session.flow_state["tatva_needs_registration"] = True
        await log_event(
            "TATVA_USER_NOT_FOUND",
            session_id=session.session_id,
            data={
                "phone": normalize_phone_for_tatva(phone),
                "message": payload.get("message"),
            },
        )
        return None

    return None


async def update_tatva_user_profile_for_session(session: Session) -> Optional[str]:
    """Update an existing Tatva user profile via register-phone."""
    if session.flow_state.get("vendor_blocked"):
        return VENDOR_BLOCKED_MESSAGE

    if not session.extracted_fields.get("tatva_user_id"):
        return None

    name = str(session.extracted_fields.get("client_name") or "").strip()
    if not name:
        return None

    email_raw = str(session.extracted_fields.get("email") or "").strip()
    email = email_raw if email_raw else None

    phone = _session_phone(session)
    payload = await register_phone_user(
        phone,
        full_name=name,
        email=email,
        session_id=session.session_id,
    )
    if not payload:
        return None

    if is_vendor_response(payload):
        session.flow_state["vendor_blocked"] = True
        session.flow_state["conversation_ended"] = True
        return VENDOR_BLOCKED_MESSAGE

    user = (payload.get("data") or {}).get("user") or {}
    if user:
        _hydrate_profile_from_user(session, user)

    await log_event(
        "TATVA_USER_PROFILE_UPDATED",
        session_id=session.session_id,
        data={
            "tatva_user_id": session.extracted_fields.get("tatva_user_id"),
            "message": payload.get("message"),
            "has_email": bool(email),
        },
    )
    return None


async def register_new_tatva_user_for_session(session: Session) -> Optional[str]:
    """
    Register a new Tatva user at the create-project Yes/No step once profile
    fields are collected. Returns VENDOR_BLOCKED_MESSAGE when isVendor is true.
    """
    if session.flow_state.get("vendor_blocked"):
        return VENDOR_BLOCKED_MESSAGE

    if not session.flow_state.get("tatva_needs_registration"):
        return None

    if session.extracted_fields.get("tatva_user_id"):
        return None

    if session.flow_state.get("tatva_user_registered"):
        return None

    name = str(session.extracted_fields.get("client_name") or "").strip()
    if not name:
        return None

    if not se.field_is_complete(session, "email"):
        return None

    if not se.field_is_complete(session, "city"):
        return None

    if not se.field_is_complete(session, "property_location"):
        return None

    if not se.field_is_complete(session, "willing_to_create_project"):
        return None

    if session.flow_state.get("tatva_register_attempted"):
        return None

    session.flow_state["tatva_register_attempted"] = True

    email_raw = str(session.extracted_fields.get("email") or "").strip()
    email = email_raw if se.is_valid_email_address(email_raw) else None

    phone = _session_phone(session)
    payload = await register_phone_user(
        phone,
        full_name=name,
        email=email,
        session_id=session.session_id,
    )
    if not payload:
        session.flow_state["tatva_register_attempted"] = False
        return None

    if is_vendor_response(payload):
        session.flow_state["vendor_blocked"] = True
        session.flow_state["conversation_ended"] = True
        await log_event(
            "TATVA_VENDOR_BLOCKED",
            session_id=session.session_id,
            data={
                "phone": normalize_phone_for_tatva(phone),
                "message": payload.get("message"),
                "source": "register_phone",
            },
        )
        return VENDOR_BLOCKED_MESSAGE

    user_id = _extract_user_id(payload)
    if not user_id:
        session.flow_state["tatva_register_attempted"] = False
        await log_event(
            "API_ERROR",
            session_id=session.session_id,
            data={"api": "tatva_register_phone", "error": "missing_user_id"},
        )
        return None

    session.extracted_fields["tatva_user_id"] = user_id
    session.flow_state["tatva_user_registered"] = True
    session.flow_state["tatva_needs_registration"] = False
    if "tatva_user_id" not in session.completed_fields:
        session.completed_fields.append("tatva_user_id")

    await log_event(
        "TATVA_USER_REGISTERED",
        session_id=session.session_id,
        data={
            "tatva_user_id": user_id,
            "created": (payload.get("data") or {}).get("created"),
            "is_vendor": False,
            "message": payload.get("message"),
            "has_email": bool(email),
        },
    )
    return None


async def register_tatva_user_for_session(session: Session) -> Optional[str]:
    """
    Ensure Tatva user exists for the session.
    New users are registered at the create-project step; existing users are hydrated from check-phone.
    """
    if session.flow_state.get("vendor_blocked"):
        return VENDOR_BLOCKED_MESSAGE

    if session.extracted_fields.get("tatva_user_id"):
        return None

    if session.flow_state.get("tatva_needs_registration"):
        return await register_new_tatva_user_for_session(session)

    if not session.flow_state.get("tatva_phone_checked"):
        blocked = await check_tatva_phone_for_session(session)
        if blocked:
            return blocked
        if session.extracted_fields.get("tatva_user_id"):
            return None
        if session.flow_state.get("tatva_needs_registration"):
            return await register_new_tatva_user_for_session(session)

    return None


def _tatva_admin_headers() -> dict[str, str]:
    headers = {
        **TATVA_HTTP_HEADERS,
        "Content-Type": "application/json",
    }
    api_key = (get_settings().admin_api_key or "").strip()
    if api_key and api_key != "changeme":
        headers["X-Admin-Key"] = api_key
    return headers


async def fetch_tatva_users(
    *,
    page: int = 1,
    limit: int = 10,
    utm_source: str | None = None,
    utm_medium: str | None = None,
) -> dict[str, Any]:
    """GET registered Tatva users for CRM admin panel."""
    settings = get_settings()
    base_url = (settings.tatva_users_api_base_url or "").rstrip("/")
    if not base_url:
        return {
            "success": False,
            "message": "Tatva API not configured",
            "data": {"users": [], "total": 0, "page": page, "limit": limit, "totalPages": 0},
        }

    params: dict[str, str | int] = {"page": max(1, page), "limit": max(1, min(limit, 100))}
    if utm_source and utm_source.strip():
        params["utm_source"] = utm_source.strip()
    if utm_medium and utm_medium.strip():
        params["utm_medium"] = utm_medium.strip()
    url = f"{base_url}{LIST_USERS_PATH}"
    try:
        async with httpx.AsyncClient(timeout=30.0, headers=_tatva_admin_headers()) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            payload = response.json()
    except httpx.HTTPStatusError as exc:
        return {
            "success": False,
            "message": str(exc),
            "data": {
                "users": [],
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
            "data": {"users": [], "total": 0, "page": page, "limit": limit, "totalPages": 0},
        }

    if not isinstance(payload, dict):
        return {
            "success": False,
            "message": "Invalid response from Tatva users API",
            "data": {"users": [], "total": 0, "page": page, "limit": limit, "totalPages": 0},
        }

    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    users = data.get("users") if isinstance(data.get("users"), list) else []
    return {
        "success": bool(payload.get("success", True)),
        "message": str(payload.get("message") or ""),
        "data": {
            "users": users,
            "total": int(data.get("total") or len(users)),
            "page": int(data.get("page") or page),
            "limit": int(data.get("limit") or limit),
            "totalPages": int(data.get("totalPages") or 1),
        },
    }


# Back-compat alias used in tests
is_vendor_register_response = is_vendor_response

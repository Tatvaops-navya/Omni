"""Fetch Tatva admin employees for lead assignment."""
from __future__ import annotations

from typing import Any
from urllib.parse import quote

import httpx

from backend.config import get_settings
from backend.integrations.tatva_users import TATVA_HTTP_HEADERS

EMPLOYEES_BY_DEPARTMENT_PATH = "/admin/api/admin/employees/by-department"
EMPLOYEES_AUTH_LOGIN_PATH = "/admin/api/admin/employees/auth/login"
EMPLOYEES_AUTH_OTP_SEND_PATH = "/admin/api/admin/employees/auth/otp/send"
EMPLOYEES_AUTH_OTP_VERIFY_PATH = "/admin/api/admin/employees/auth/otp/verify"


def _employees_headers() -> dict[str, str]:
    headers = {
        **TATVA_HTTP_HEADERS,
        "Content-Type": "application/json",
    }
    api_key = (get_settings().admin_api_key or "").strip()
    if api_key and api_key != "changeme":
        headers["X-Admin-Key"] = api_key
    return headers


def _extract_employees(data: dict[str, Any]) -> list[dict[str, Any]]:
    if isinstance(data.get("employees"), list):
        return [e for e in data["employees"] if isinstance(e, dict)]
    if isinstance(data.get("items"), list):
        return [e for e in data["items"] if isinstance(e, dict)]
    if isinstance(data, list):
        return [e for e in data if isinstance(e, dict)]
    return []


async def fetch_tatva_employees(
    *,
    department: str = "sales",
    page: int = 1,
    limit: int = 50,
) -> dict[str, Any]:
    """GET employees by department from Tatva admin API."""
    settings = get_settings()
    base_url = (settings.tatva_users_api_base_url or "").rstrip("/")
    if not base_url:
        return {
            "success": False,
            "message": "Tatva API not configured",
            "data": {"employees": []},
        }

    dept = (department or "sales").strip() or "sales"
    if dept.lower() == "rm":
        url = f"{base_url}/admin/api/admin/employees"
        params = {
            "department": dept,
            "page": max(1, page),
            "limit": max(1, min(limit, 100)),
        }
    else:
        url = f"{base_url}{EMPLOYEES_BY_DEPARTMENT_PATH}/{quote(dept, safe='')}"
        params = {"page": max(1, page), "limit": max(1, min(limit, 100))}

    try:
        async with httpx.AsyncClient(timeout=30.0, headers=_employees_headers()) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            payload = response.json()
    except httpx.HTTPStatusError as exc:
        return {
            "success": False,
            "message": str(exc),
            "data": {"employees": []},
            "error_status": exc.response.status_code,
        }
    except Exception as exc:
        return {
            "success": False,
            "message": str(exc),
            "data": {"employees": []},
        }

    if not isinstance(payload, dict):
        return {
            "success": False,
            "message": "Invalid response from Tatva employees API",
            "data": {"employees": []},
        }

    raw_data = payload.get("data")
    if isinstance(raw_data, list):
        employees = [e for e in raw_data if isinstance(e, dict)]
    elif isinstance(raw_data, dict):
        employees = _extract_employees(raw_data)
    else:
        employees = _extract_employees(payload)

    pagination = {}
    if isinstance(raw_data, dict) and isinstance(raw_data.get("pagination"), dict):
        pagination = raw_data["pagination"]

    return {
        "success": bool(payload.get("success", True)),
        "message": str(payload.get("message") or ""),
        "data": {
            "employees": employees,
            "pagination": pagination,
        },
    }


def _pick_str(*values: Any) -> str:
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return ""


def decode_jwt_claims(token: str) -> dict[str, Any]:
    """Decode Tatva JWT payload (no signature verify — used after Tatva login)."""
    import base64
    import json

    try:
        part = (token or "").split(".")[1]
        if not part:
            return {}
        padding = "=" * (-len(part) % 4)
        raw = base64.urlsafe_b64decode(part + padding)
        data = json.loads(raw.decode("utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def user_from_tatva_access_token(token: str, *, fallback_email: str = "") -> dict[str, Any]:
    """Build normalized user dict from Tatva accessToken claims."""
    claims = decode_jwt_claims(token)
    email = _pick_str(claims.get("email"), fallback_email)
    user_id = _pick_str(claims.get("_id"), claims.get("id"), claims.get("sub"))
    role_name = _pick_str(claims.get("role"), claims.get("roleName"))
    display = role_name.replace("_", " ").title() if role_name else ""
    if not display and email:
        display = email.split("@")[0].replace(".", " ").title()
    return {
        "id": user_id or None,
        "name": display or "Admin",
        "email": email or None,
        "role_name": role_name or None,
        "department": None,
    }


def _extract_access_token(payload: dict[str, Any]) -> str | None:
    """Pull Tatva JWT from login/OTP payloads (`data.accessToken`)."""
    data = payload.get("data")
    candidates: list[Any] = [
        payload.get("accessToken"),
        payload.get("access_token"),
        payload.get("token"),
    ]
    if isinstance(data, dict):
        candidates.extend(
            [
                data.get("accessToken"),
                data.get("access_token"),
                data.get("token"),
            ]
        )
    for value in candidates:
        text = _pick_str(value)
        if text:
            return text
    return None


def _extract_employee_user(payload: dict[str, Any]) -> dict[str, Any]:
    """Normalize Tatva employee login/OTP payload into id/name/email fields."""
    data = payload.get("data")
    candidates: list[Any] = [
        data,
        payload.get("employee"),
        payload.get("user"),
        payload,
    ]
    if isinstance(data, dict):
        candidates.extend(
            [
                data.get("employee"),
                data.get("user"),
                data.get("admin"),
                data.get("profile"),
            ]
        )

    for item in candidates:
        if not isinstance(item, dict):
            continue
        email = _pick_str(item.get("email"), item.get("Email"))
        name = _pick_str(
            item.get("fullName"),
            item.get("name"),
            item.get("userName"),
            item.get("username"),
        )
        user_id = _pick_str(item.get("_id"), item.get("id"), item.get("employeeId"))
        phone = _pick_str(
            item.get("phoneNumber"),
            item.get("phone"),
            item.get("mobile"),
        )
        role_raw = item.get("role")
        if isinstance(role_raw, dict):
            role_name = _pick_str(role_raw.get("name"), role_raw.get("title"))
        else:
            role_name = _pick_str(role_raw, item.get("designation"))
        department = item.get("department")
        if isinstance(department, list) and department:
            first = department[0]
            dept_name = _pick_str(
                first.get("name") if isinstance(first, dict) else first,
            )
        elif isinstance(department, dict):
            dept_name = _pick_str(department.get("name"))
        else:
            dept_name = _pick_str(department)
        if email or name or user_id or phone:
            return {
                "id": user_id or None,
                "name": name or email or phone or "Team",
                "email": email or None,
                "phone": phone or None,
                "role_name": role_name or None,
                "department": dept_name or None,
            }
    return {"id": None, "name": "Team", "email": None, "phone": None}


def extract_employee_user_from_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Public wrapper used by admin team-session after browser OTP verify."""
    if not isinstance(payload, dict):
        return {"id": None, "name": "Team", "email": None, "phone": None}
    return _extract_employee_user(payload)


def _normalize_otp_phone(phone_number: str) -> str:
    from backend.integrations.tatva_users import normalize_phone_for_tatva

    return normalize_phone_for_tatva(phone_number)


async def send_tatva_employee_otp(*, phone_number: str) -> dict[str, Any]:
    """
    POST /admin/api/admin/employees/auth/otp/send
    Body: { "phoneNumber": "8959896246" }
    """
    settings = get_settings()
    base_url = (settings.tatva_users_api_base_url or "").rstrip("/")
    if not base_url:
        return {
            "success": False,
            "message": "Tatva API not configured",
            "error_status": 503,
        }

    phone = _normalize_otp_phone(phone_number)
    if len(phone) != 10:
        return {
            "success": False,
            "message": "Enter a valid 10-digit mobile number",
            "error_status": 400,
        }

    url = f"{base_url}{EMPLOYEES_AUTH_OTP_SEND_PATH}"
    try:
        async with httpx.AsyncClient(timeout=30.0, headers=_employees_headers()) as client:
            response = await client.post(url, json={"phoneNumber": phone})
            try:
                payload = response.json()
            except Exception:
                payload = {}
            if not isinstance(payload, dict):
                payload = {}

            if response.status_code >= 400:
                return {
                    "success": False,
                    "message": _pick_str(
                        payload.get("message"),
                        payload.get("detail"),
                        payload.get("error"),
                        f"Failed to send OTP ({response.status_code})",
                    ),
                    "error_status": response.status_code,
                    "raw": payload,
                }

            if payload.get("success") is False:
                return {
                    "success": False,
                    "message": _pick_str(payload.get("message"), "Failed to send OTP"),
                    "error_status": 400,
                    "raw": payload,
                }

            return {
                "success": True,
                "message": _pick_str(payload.get("message"), "OTP sent"),
                "raw": payload,
            }
    except Exception as exc:
        return {
            "success": False,
            "message": str(exc) or "Tatva OTP send failed",
            "error_status": 502,
        }


async def verify_tatva_employee_otp(*, phone_number: str, otp: str) -> dict[str, Any]:
    """
    POST /admin/api/admin/employees/auth/otp/verify
    Body: { "phoneNumber": "8959896246", "otp": "413250" }
    """
    settings = get_settings()
    base_url = (settings.tatva_users_api_base_url or "").rstrip("/")
    if not base_url:
        return {
            "success": False,
            "message": "Tatva API not configured",
            "user": None,
            "error_status": 503,
        }

    phone = _normalize_otp_phone(phone_number)
    code = (otp or "").strip()
    if len(phone) != 10:
        return {
            "success": False,
            "message": "Enter a valid 10-digit mobile number",
            "user": None,
            "error_status": 400,
        }
    if not code:
        return {
            "success": False,
            "message": "OTP is required",
            "user": None,
            "error_status": 400,
        }

    url = f"{base_url}{EMPLOYEES_AUTH_OTP_VERIFY_PATH}"
    body = {"phoneNumber": phone, "otp": code}
    try:
        async with httpx.AsyncClient(timeout=30.0, headers=_employees_headers()) as client:
            response = await client.post(url, json=body)
            try:
                payload = response.json()
            except Exception:
                payload = {}
            if not isinstance(payload, dict):
                payload = {}

            if response.status_code >= 400:
                return {
                    "success": False,
                    "message": _pick_str(
                        payload.get("message"),
                        payload.get("detail"),
                        payload.get("error"),
                        f"OTP verification failed ({response.status_code})",
                    ),
                    "user": None,
                    "error_status": response.status_code,
                    "raw": payload,
                }

            if payload.get("success") is False:
                return {
                    "success": False,
                    "message": _pick_str(payload.get("message"), "Invalid OTP"),
                    "user": None,
                    "error_status": 401,
                    "raw": payload,
                }

            user = _extract_employee_user(payload)
            if not user.get("phone"):
                user["phone"] = phone
            return {
                "success": True,
                "message": _pick_str(payload.get("message"), "OTP verified"),
                "user": user,
                "access_token": _extract_access_token(payload),
                "raw": payload,
            }
    except Exception as exc:
        return {
            "success": False,
            "message": str(exc) or "Tatva OTP verify failed",
            "user": None,
            "error_status": 502,
        }


async def login_tatva_employee(*, email: str, password: str) -> dict[str, Any]:
    """
    POST /admin/api/admin/employees/auth/login
    Body: { "email": "...", "password": "..." }
    """
    settings = get_settings()
    base_url = (settings.tatva_users_api_base_url or "").rstrip("/")
    if not base_url:
        return {
            "success": False,
            "message": "Tatva API not configured",
            "user": None,
        }

    url = f"{base_url}{EMPLOYEES_AUTH_LOGIN_PATH}"
    body = {
        "email": (email or "").strip().lower(),
        "password": password or "",
    }
    if not body["email"] or not body["password"]:
        return {
            "success": False,
            "message": "Email and password are required",
            "user": None,
            "error_status": 400,
        }

    try:
        async with httpx.AsyncClient(timeout=30.0, headers=_employees_headers()) as client:
            response = await client.post(url, json=body)
            try:
                payload = response.json()
            except Exception:
                payload = {}
            if not isinstance(payload, dict):
                payload = {}

            if response.status_code >= 400:
                message = _pick_str(
                    payload.get("message"),
                    payload.get("detail"),
                    payload.get("error"),
                    f"Login failed ({response.status_code})",
                )
                return {
                    "success": False,
                    "message": message,
                    "user": None,
                    "error_status": response.status_code,
                    "raw": payload,
                }

            success_flag = payload.get("success")
            if success_flag is False:
                return {
                    "success": False,
                    "message": _pick_str(payload.get("message"), "Invalid credentials"),
                    "user": None,
                    "error_status": 401,
                    "raw": payload,
                }

            user = _extract_employee_user(payload)
            if not user.get("email"):
                user["email"] = body["email"]
            return {
                "success": True,
                "message": _pick_str(payload.get("message"), "Login successful"),
                "user": user,
                "access_token": _extract_access_token(payload),
                "raw": payload,
            }
    except Exception as exc:
        return {
            "success": False,
            "message": str(exc) or "Tatva login request failed",
            "user": None,
            "error_status": 502,
        }

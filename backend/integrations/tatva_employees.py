"""Fetch Tatva admin employees for lead assignment."""
from __future__ import annotations

from typing import Any
from urllib.parse import quote

import httpx

from backend.config import get_settings
from backend.integrations.tatva_users import TATVA_HTTP_HEADERS

EMPLOYEES_BY_DEPARTMENT_PATH = "/admin/api/admin/employees/by-department"


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

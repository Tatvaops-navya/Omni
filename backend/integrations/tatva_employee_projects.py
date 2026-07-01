"""Fetch Tatva employee project assignments."""
from __future__ import annotations

from typing import Any
from urllib.parse import quote

import httpx

from backend.config import get_settings
from backend.integrations.tatva_employees import fetch_tatva_employees
from backend.integrations.tatva_users import TATVA_HTTP_HEADERS

EMPLOYEE_PROJECTS_PATH = "/admin/api/admin/employees"


def _headers() -> dict[str, str]:
    headers = {
        **TATVA_HTTP_HEADERS,
        "Content-Type": "application/json",
    }
    api_key = (get_settings().admin_api_key or "").strip()
    if api_key and api_key != "changeme":
        headers["X-Admin-Key"] = api_key
    return headers


def _extract_projects(payload: dict[str, Any]) -> list[dict[str, Any]]:
    if isinstance(payload.get("projects"), list):
        return [p for p in payload["projects"] if isinstance(p, dict)]
    raw = payload.get("data")
    if isinstance(raw, list):
        return [p for p in raw if isinstance(p, dict)]
    if isinstance(raw, dict):
        for key in ("projects", "items", "assignments"):
            value = raw.get(key)
            if isinstance(value, list):
                return [p for p in value if isinstance(p, dict)]
    if isinstance(payload.get("items"), list):
        return [p for p in payload["items"] if isinstance(p, dict)]
    return []


async def fetch_employee_projects(employee_id: str) -> dict[str, Any]:
    """GET projects assigned to a Tatva employee."""
    settings = get_settings()
    base_url = (settings.tatva_users_api_base_url or "").rstrip("/")
    emp_id = (employee_id or "").strip()
    if not base_url or not emp_id:
        return {
            "success": False,
            "message": "Tatva API or employee id not configured",
            "data": {"items": [], "employee_id": emp_id},
        }

    url = f"{base_url}{EMPLOYEE_PROJECTS_PATH}/{quote(emp_id, safe='')}/projects"

    try:
        async with httpx.AsyncClient(timeout=30.0, headers=_headers()) as client:
            response = await client.get(url)
            response.raise_for_status()
            payload = response.json()
    except httpx.HTTPStatusError as exc:
        return {
            "success": False,
            "message": str(exc),
            "data": {"items": [], "employee_id": emp_id},
            "error_status": exc.response.status_code,
        }
    except Exception as exc:
        return {
            "success": False,
            "message": str(exc),
            "data": {"items": [], "employee_id": emp_id},
        }

    if not isinstance(payload, dict):
        return {
            "success": False,
            "message": "Invalid response from Tatva projects API",
            "data": {"items": [], "employee_id": emp_id},
        }

    projects = _extract_projects(payload)
    raw_data = payload.get("data")
    pagination: dict[str, Any] = {}
    if isinstance(raw_data, dict) and isinstance(raw_data.get("pagination"), dict):
        pagination = raw_data["pagination"]

    return {
        "success": bool(payload.get("success", True)),
        "message": str(payload.get("message") or ""),
        "data": {
            "items": projects,
            "employee_id": emp_id,
            "total": int(pagination.get("total") or len(projects)),
            "pagination": pagination,
        },
    }


async def resolve_employee_id_by_email(email: str) -> str | None:
    """Match Tatva employee _id by email across common departments."""
    needle = (email or "").strip().lower()
    if not needle:
        return None

    for department in ("sales", "presales", "operations", "design", "project", "rm"):
        result = await fetch_tatva_employees(department=department, page=1, limit=100)
        employees = result.get("data", {}).get("employees", [])
        if not isinstance(employees, list):
            continue
        for emp in employees:
            if not isinstance(emp, dict):
                continue
            emp_email = str(emp.get("email") or "").strip().lower()
            if emp_email == needle:
                emp_id = str(emp.get("_id") or emp.get("id") or emp.get("employeeId") or "").strip()
                if emp_id:
                    return emp_id
    return None

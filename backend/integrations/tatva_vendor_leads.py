"""
Fetch vendor leads from Tatva admin API for CRM admin panel.
GET /admin/api/admin/vendor-leads
"""
from __future__ import annotations

from typing import Any

import httpx

from backend.config import get_settings
from backend.integrations.tatva_users import TATVA_HTTP_HEADERS

VENDOR_LEADS_PATH = "/admin/api/admin/vendor-leads"


def _vendor_leads_headers() -> dict[str, str]:
    headers = {
        **TATVA_HTTP_HEADERS,
        "Content-Type": "application/json",
    }
    api_key = (get_settings().admin_api_key or "").strip()
    if api_key and api_key != "changeme":
        headers["X-Admin-Key"] = api_key
    return headers


def _extract_items(data: dict[str, Any]) -> list[Any]:
    for key in ("items", "vendorLeads", "vendor_leads", "leads"):
        value = data.get(key)
        if isinstance(value, list):
            return value
    return []


async def fetch_vendor_leads(
    *,
    page: int = 1,
    limit: int = 20,
    status: str | None = None,
) -> dict[str, Any]:
    """GET vendor leads list from Tatva admin API."""
    settings = get_settings()
    base_url = (settings.tatva_users_api_base_url or "").rstrip("/")
    if not base_url:
        return {
            "success": False,
            "message": "Tatva API not configured",
            "data": {"items": [], "total": 0, "page": page, "limit": limit, "totalPages": 0},
        }

    params: dict[str, str | int] = {
        "page": max(1, page),
        "limit": max(1, min(limit, 100)),
    }
    if status and status.strip():
        params["status"] = status.strip()
    url = f"{base_url}{VENDOR_LEADS_PATH}"
    try:
        async with httpx.AsyncClient(timeout=30.0, headers=_vendor_leads_headers()) as client:
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
            "message": "Invalid response from Tatva vendor-leads API",
            "data": {"items": [], "total": 0, "page": page, "limit": limit, "totalPages": 0},
        }

    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    items = _extract_items(data)
    pagination = data.get("pagination") if isinstance(data.get("pagination"), dict) else {}
    return {
        "success": bool(payload.get("success", True)),
        "message": str(payload.get("message") or ""),
        "data": {
            "items": items,
            "total": int(pagination.get("total") or data.get("total") or len(items)),
            "page": int(pagination.get("page") or data.get("page") or page),
            "limit": int(pagination.get("limit") or data.get("limit") or limit),
            "totalPages": int(
                pagination.get("pages") or pagination.get("totalPages") or data.get("totalPages") or 1
            ),
        },
    }

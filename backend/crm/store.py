"""Supabase persistence for CRM users and lead assignments."""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any, Optional

from backend.config import get_settings
from backend.storage.supabase_client import get_supabase_client, is_supabase_configured

SOURCE_TATVA_PRESALES = "tatva_presales"

STATUS_UNASSIGNED = "unassigned"
STATUS_ASSIGNED = "assigned"
STATUS_IN_PROGRESS = "in_progress"
STATUS_PRESALES_COMPLETED = "presales_completed"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def hash_password(password: str) -> str:
    pepper = (get_settings().crm_password_pepper or "tatvaops-crm").strip()
    return hashlib.sha256(f"{password}:{pepper}".encode()).hexdigest()


def verify_password(password: str, password_hash: str) -> bool:
    return hash_password(password) == password_hash


def _client():
    client = get_supabase_client()
    if client is None:
        raise RuntimeError("Supabase is not configured")
    return client


def crm_available() -> bool:
    return is_supabase_configured()


def list_crm_users(*, role: str | None = None, active_only: bool = True) -> list[dict[str, Any]]:
    if not crm_available():
        return []
    query = _client().table("crm_users").select(
        "id,name,email,role,active,created_at,updated_at"
    )
    if role:
        query = query.eq("role", role)
    if active_only:
        query = query.eq("active", True)
    result = query.order("name").execute()
    return list(result.data or [])


def get_crm_user_by_email(email: str) -> Optional[dict[str, Any]]:
    if not crm_available():
        return None
    result = (
        _client()
        .table("crm_users")
        .select("id,name,email,role,active,password_hash")
        .eq("email", email.strip().lower())
        .limit(1)
        .execute()
    )
    rows = result.data or []
    return rows[0] if rows else None


def create_crm_user(
    *,
    name: str,
    email: str,
    password: str,
    role: str,
) -> dict[str, Any]:
    if role not in {"admin", "presales", "rm"}:
        raise ValueError("invalid role")
    row = {
        "name": name.strip(),
        "email": email.strip().lower(),
        "password_hash": hash_password(password),
        "role": role,
        "active": True,
        "updated_at": _now_iso(),
    }
    result = _client().table("crm_users").insert(row).execute()
    data = (result.data or [None])[0]
    if not data:
        raise RuntimeError("Failed to create CRM user")
    return data


def get_assignments_by_external_ids(
    external_ids: list[str],
    *,
    source: str = SOURCE_TATVA_PRESALES,
) -> dict[str, dict[str, Any]]:
    if not crm_available() or not external_ids:
        return {}
    result = (
        _client()
        .table("lead_assignments")
        .select("*")
        .eq("source", source)
        .in_("external_id", external_ids)
        .execute()
    )
    out: dict[str, dict[str, Any]] = {}
    for row in result.data or []:
        out[str(row.get("external_id"))] = row
    return out


def assign_presales_lead(
    *,
    external_id: str,
    presales_user_id: str,
    snapshot: dict[str, Any],
    source: str = SOURCE_TATVA_PRESALES,
) -> dict[str, Any]:
    now = _now_iso()
    row = {
        "source": source,
        "external_id": external_id,
        "presales_user_id": presales_user_id,
        "status": STATUS_ASSIGNED,
        "snapshot": snapshot,
        "assigned_at": now,
        "updated_at": now,
    }
    result = (
        _client()
        .table("lead_assignments")
        .upsert(row, on_conflict="source,external_id")
        .execute()
    )
    data = (result.data or [None])[0]
    if not data:
        raise RuntimeError("Failed to assign lead")
    return data


def list_my_leads(
    *,
    presales_user_id: str,
    page: int = 1,
    limit: int = 20,
    status: str | None = None,
) -> dict[str, Any]:
    if not crm_available():
        return {"items": [], "total": 0, "page": page, "limit": limit, "totalPages": 0}

    query = (
        _client()
        .table("lead_assignments")
        .select("*", count="exact")
        .eq("source", SOURCE_TATVA_PRESALES)
        .eq("presales_user_id", presales_user_id)
    )
    if status:
        query = query.eq("status", status)

    offset = (max(1, page) - 1) * limit
    result = (
        query.order("assigned_at", desc=True)
        .range(offset, offset + limit - 1)
        .execute()
    )
    total = int(result.count or 0)
    items = list(result.data or [])
    total_pages = max(1, (total + limit - 1) // limit) if total else 1
    return {
        "items": items,
        "total": total,
        "page": page,
        "limit": limit,
        "totalPages": total_pages,
    }


def mark_presales_completed(
    *,
    external_id: str,
    presales_user_id: str,
    notes: str | None = None,
) -> dict[str, Any]:
    now = _now_iso()
    update: dict[str, Any] = {
        "status": STATUS_PRESALES_COMPLETED,
        "presales_completed_at": now,
        "updated_at": now,
    }
    if notes is not None:
        update["notes"] = notes
    result = (
        _client()
        .table("lead_assignments")
        .update(update)
        .eq("source", SOURCE_TATVA_PRESALES)
        .eq("external_id", external_id)
        .eq("presales_user_id", presales_user_id)
        .execute()
    )
    data = (result.data or [None])[0]
    if not data:
        raise RuntimeError("Lead not found or not assigned to you")
    return data


def enrich_presales_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Merge Tatva presales rows with Supabase assignment metadata."""
    if not items:
        return []
    ids = [str(i.get("_id") or "") for i in items if i.get("_id")]
    assignments = get_assignments_by_external_ids(ids)
    users_by_id = {u["id"]: u for u in list_crm_users(active_only=True)}
    enriched: list[dict[str, Any]] = []
    for item in items:
        ext_id = str(item.get("_id") or "")
        assignment = assignments.get(ext_id) or {}
        assignee = None
        pid = assignment.get("presales_user_id")
        if pid and pid in users_by_id:
            assignee = users_by_id[pid]
        enriched.append({
            **item,
            "assignment": {
                "status": assignment.get("status") or STATUS_UNASSIGNED,
                "presales_user_id": pid,
                "assignee_name": (assignee or {}).get("name"),
                "assignee_email": (assignee or {}).get("email"),
                "assigned_at": assignment.get("assigned_at"),
                "notes": assignment.get("notes"),
            },
        })
    return enriched

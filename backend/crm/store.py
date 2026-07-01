"""Supabase persistence for CRM users and lead assignments."""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any, Optional

from backend.config import get_settings
from backend.storage.supabase_client import get_supabase_client, is_supabase_configured

SOURCE_TATVA_PRESALES = "tatva_presales"
SOURCE_TATVA_VENDOR = "tatva_vendor"

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


def _staff_column_for_role(role: str) -> str:
    if role == "presales":
        return "presales_user_id"
    if role == "rm":
        return "rm_user_id"
    raise ValueError("invalid staff role")


def get_crm_user_by_id(user_id: str) -> Optional[dict[str, Any]]:
    if not crm_available():
        return None
    result = (
        _client()
        .table("crm_users")
        .select("id,name,email,role,active")
        .eq("id", user_id)
        .limit(1)
        .execute()
    )
    rows = result.data or []
    return rows[0] if rows else None


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
    return assign_staff_lead(
        external_id=external_id,
        staff_user_id=presales_user_id,
        staff_role="presales",
        snapshot=snapshot,
        source=source,
    )


def assign_staff_lead(
    *,
    external_id: str,
    staff_user_id: str,
    staff_role: str,
    snapshot: dict[str, Any],
    source: str,
) -> dict[str, Any]:
    col = _staff_column_for_role(staff_role)
    now = _now_iso()
    row: dict[str, Any] = {
        "source": source,
        "external_id": external_id,
        "status": STATUS_ASSIGNED,
        "snapshot": snapshot,
        "assigned_at": now,
        "updated_at": now,
        col: staff_user_id,
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


def delete_assignment(
    *,
    external_id: str,
    source: str = SOURCE_TATVA_PRESALES,
) -> bool:
    if not crm_available():
        return False
    (
        _client()
        .table("lead_assignments")
        .delete()
        .eq("source", source)
        .eq("external_id", external_id)
        .execute()
    )
    return True


def list_my_leads(
    *,
    staff_user_id: str,
    staff_role: str,
    source: str = SOURCE_TATVA_PRESALES,
    page: int = 1,
    limit: int = 20,
    status: str | None = None,
) -> dict[str, Any]:
    if not crm_available():
        return {"items": [], "total": 0, "page": page, "limit": limit, "totalPages": 0}

    col = _staff_column_for_role(staff_role)
    query = (
        _client()
        .table("lead_assignments")
        .select("*", count="exact")
        .eq("source", source)
        .eq(col, staff_user_id)
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
    return mark_lead_completed(
        external_id=external_id,
        staff_user_id=presales_user_id,
        staff_role="presales",
        source=SOURCE_TATVA_PRESALES,
        notes=notes,
    )


def mark_lead_completed(
    *,
    external_id: str,
    staff_user_id: str,
    staff_role: str,
    source: str,
    notes: str | None = None,
) -> dict[str, Any]:
    col = _staff_column_for_role(staff_role)
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
        .eq("source", source)
        .eq("external_id", external_id)
        .eq(col, staff_user_id)
        .execute()
    )
    data = (result.data or [None])[0]
    if not data:
        raise RuntimeError("Lead not found or not assigned to you")
    return data


def update_lead_notes(
    *,
    external_id: str,
    staff_user_id: str,
    staff_role: str,
    source: str,
    notes: str,
) -> dict[str, Any]:
    col = _staff_column_for_role(staff_role)
    now = _now_iso()
    result = (
        _client()
        .table("lead_assignments")
        .update({"notes": notes, "updated_at": now})
        .eq("source", source)
        .eq("external_id", external_id)
        .eq(col, staff_user_id)
        .execute()
    )
    data = (result.data or [None])[0]
    if not data:
        raise RuntimeError("Lead not found or not assigned to you")
    return data


def normalize_phone(phone: str) -> str:
    digits = "".join(c for c in (phone or "") if c.isdigit())
    if len(digits) >= 10:
        return digits[-10:]
    return digits


def assigned_phones_for_staff(
    staff_user_id: str,
    staff_role: str,
    *,
    source: str | None = SOURCE_TATVA_PRESALES,
) -> set[str]:
    """Phone numbers from leads assigned to this presales/RM team member."""
    if not crm_available():
        return set()
    col = _staff_column_for_role(staff_role)
    query = (
        _client()
        .table("lead_assignments")
        .select("snapshot")
        .eq(col, staff_user_id)
    )
    if source:
        query = query.eq("source", source)
    result = query.execute()
    phones: set[str] = set()
    phone_keys = ("phoneNumber", "phone", "phone_number", "mobile")
    for row in result.data or []:
        snap = row.get("snapshot") if isinstance(row.get("snapshot"), dict) else {}
        for key in phone_keys:
            raw = snap.get(key)
            if raw:
                norm = normalize_phone(str(raw))
                if norm:
                    phones.add(norm)
                    break
    return phones


def enquiry_phone_keys(enquiry: dict[str, Any]) -> set[str]:
    phones: set[str] = set()
    candidates = [enquiry.get("phone_number")]
    fields = enquiry.get("extracted_fields")
    if isinstance(fields, dict):
        candidates.append(fields.get("phone_number"))
    for raw in candidates:
        if raw:
            norm = normalize_phone(str(raw))
            if norm:
                phones.add(norm)
    return phones


def enquiry_matches_assigned_phones(
    enquiry: dict[str, Any],
    assigned_phones: set[str],
) -> bool:
    if not assigned_phones:
        return False
    return bool(enquiry_phone_keys(enquiry) & assigned_phones)


TATVA_EMPLOYEE_PREFIX = "tatva:"


def _tatva_assignee_from_snapshot(assignment: dict[str, Any]) -> tuple[str | None, str | None]:
    snap = assignment.get("snapshot") or {}
    te = snap.get("tatva_employee") if isinstance(snap, dict) else None
    if not isinstance(te, dict):
        return None, None
    name = str(te.get("name") or "").strip() or None
    email = str(te.get("email") or "").strip() or None
    return name, email


def assign_tatva_employee_lead(
    *,
    external_id: str,
    employee_id: str,
    employee_name: str = "",
    employee_email: str = "",
    employee_department: str = "",
    employee_role: str = "",
    snapshot: dict[str, Any],
    source: str = SOURCE_TATVA_PRESALES,
) -> dict[str, Any]:
    staff_id = f"{TATVA_EMPLOYEE_PREFIX}{employee_id}"
    full_snapshot = {
        **snapshot,
        "tatva_employee": {
            "id": employee_id,
            "name": employee_name,
            "email": employee_email,
            "department": employee_department,
            "role": employee_role,
        },
    }
    return assign_staff_lead(
        external_id=external_id,
        staff_user_id=staff_id,
        staff_role="presales",
        snapshot=full_snapshot,
        source=source,
    )


def _assignment_meta(
    assignment: dict[str, Any],
    users_by_id: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    pid = assignment.get("presales_user_id")
    rid = assignment.get("rm_user_id")
    assignee_id = pid or rid
    assignee = users_by_id.get(assignee_id) if assignee_id else None
    assignee_name = (assignee or {}).get("name")
    assignee_email = (assignee or {}).get("email")
    if assignee_id and str(assignee_id).startswith(TATVA_EMPLOYEE_PREFIX):
        te_name, te_email = _tatva_assignee_from_snapshot(assignment)
        assignee_name = te_name or assignee_name
        assignee_email = te_email or assignee_email
    return {
        "status": assignment.get("status") or STATUS_UNASSIGNED,
        "presales_user_id": pid,
        "rm_user_id": rid,
        "staff_user_id": assignee_id,
        "assignee_name": assignee_name,
        "assignee_email": assignee_email,
        "assigned_at": assignment.get("assigned_at"),
        "notes": assignment.get("notes"),
    }


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
        enriched.append({
            **item,
            "assignment": _assignment_meta(assignment, users_by_id),
        })
    return enriched


def enrich_vendor_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Merge Tatva vendor lead rows with Supabase assignment metadata."""
    if not items:
        return []
    ids = [
        str(i.get("_id") or i.get("id") or "")
        for i in items
        if i.get("_id") or i.get("id")
    ]
    assignments = get_assignments_by_external_ids(ids, source=SOURCE_TATVA_VENDOR)
    users_by_id = {u["id"]: u for u in list_crm_users(active_only=True)}
    enriched: list[dict[str, Any]] = []
    for item in items:
        ext_id = str(item.get("_id") or item.get("id") or "")
        assignment = assignments.get(ext_id) or {}
        enriched.append({
            **item,
            "assignment": _assignment_meta(assignment, users_by_id),
        })
    return enriched

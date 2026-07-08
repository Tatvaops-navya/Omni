"""Supabase persistence for CRM users and lead assignments."""
from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from backend.config import get_settings
from backend.storage.supabase_client import get_supabase_client, is_supabase_configured

SOURCE_TATVA_PRESALES = "tatva_presales"
SOURCE_TATVA_PRESALES_VENDOR = "tatva_presales_vendor"
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


TEAM_COMMENT_LOG_KEY = "__team_comment_log"
CUSTOM_PROGRESS_STAGES_KEY = "__custom_progress_stages"
TATVA_EMPLOYEE_PREFIX = "tatva:"
VALID_PROGRESS_ANCHORS = frozenset({
    STATUS_UNASSIGNED,
    STATUS_ASSIGNED,
    STATUS_IN_PROGRESS,
})


def comment_log_from_assignment(assignment: dict[str, Any]) -> list[dict[str, Any]]:
    """Return chronological team comment entries for a lead assignment."""
    snap = assignment.get("snapshot") if isinstance(assignment.get("snapshot"), dict) else {}
    stored = snap.get(TEAM_COMMENT_LOG_KEY)
    if isinstance(stored, list):
        entries = [
            _normalize_comment_entry(e)
            for e in stored
            if isinstance(e, dict) and str(e.get("text") or "").strip()
        ]
        if entries:
            return entries

    notes = str(assignment.get("notes") or "").strip()
    if notes:
        return [{
            "text": notes,
            "created_at": assignment.get("updated_at") or assignment.get("assigned_at") or _now_iso(),
            "author_id": None,
            "author_name": None,
        }]
    return []


def _normalize_comment_entry(entry: dict[str, Any]) -> dict[str, Any]:
    return {
        "text": str(entry.get("text") or "").strip(),
        "created_at": entry.get("created_at"),
        "author_id": entry.get("author_id"),
        "author_name": entry.get("author_name"),
    }


def _snapshot_with_comment_log(snapshot: dict[str, Any], log: list[dict[str, Any]]) -> dict[str, Any]:
    merged = dict(snapshot)
    merged[TEAM_COMMENT_LOG_KEY] = log
    return merged


def progress_stages_from_assignment(assignment: dict[str, Any]) -> list[dict[str, Any]]:
    """Return custom progress stages stored on a lead assignment."""
    snap = assignment.get("snapshot") if isinstance(assignment.get("snapshot"), dict) else {}
    stored = snap.get(CUSTOM_PROGRESS_STAGES_KEY)
    if not isinstance(stored, list):
        return []
    raw_entries = [e for e in stored if isinstance(e, dict)]
    known_ids = frozenset(
        str(entry.get("id") or "").strip()
        for entry in raw_entries
        if str(entry.get("id") or "").strip()
    )
    stages: list[dict[str, Any]] = []
    for entry in raw_entries:
        normalized = _normalize_progress_stage(entry, known_ids)
        if normalized["id"] and normalized["title"]:
            stages.append(normalized)
    stages.sort(key=lambda s: str(s.get("created_at") or ""))
    return stages


def _normalize_progress_stage(
    entry: dict[str, Any],
    known_stage_ids: frozenset[str] | None = None,
) -> dict[str, Any]:
    raw_anchor = str(entry.get("insert_after") or STATUS_ASSIGNED).strip()
    lowered = raw_anchor.lower()
    if lowered in VALID_PROGRESS_ANCHORS:
        insert_after = lowered
    elif known_stage_ids and raw_anchor in known_stage_ids:
        insert_after = raw_anchor
    else:
        insert_after = STATUS_ASSIGNED
    title = str(entry.get("title") or "").strip()
    description = str(entry.get("description") or "").strip()
    return {
        "id": str(entry.get("id") or "").strip(),
        "title": title,
        "description": description or None,
        "insert_after": insert_after,
        "completed_at": entry.get("completed_at"),
        "created_at": entry.get("created_at"),
        "created_by_name": entry.get("created_by_name"),
    }


def _snapshot_with_progress_stages(
    snapshot: dict[str, Any],
    stages: list[dict[str, Any]],
) -> dict[str, Any]:
    merged = dict(snapshot)
    merged[CUSTOM_PROGRESS_STAGES_KEY] = stages
    return merged


def _merge_assignment_snapshot(
    current: dict[str, Any],
    updates: dict[str, Any],
) -> dict[str, Any]:
    snap = current.get("snapshot") if isinstance(current.get("snapshot"), dict) else {}
    merged = {**snap, **updates}
    log = comment_log_from_assignment(current)
    if log:
        merged[TEAM_COMMENT_LOG_KEY] = log
    stages = progress_stages_from_assignment(current)
    if stages:
        merged[CUSTOM_PROGRESS_STAGES_KEY] = stages
    return merged


def get_or_create_assignment_for_progress(
    *,
    external_id: str,
    source: str,
    staff_user_id: str | None = None,
    staff_role: str | None = None,
    staff_email: str | None = None,
) -> dict[str, Any]:
    """Find or create a lead assignment row used for progress tracking."""
    ext_id = (external_id or "").strip()
    if not ext_id:
        raise ValueError("Missing lead id")

    if staff_user_id and staff_role:
        current = get_assignment_for_staff(
            external_id=ext_id,
            staff_user_id=staff_user_id,
            staff_role=staff_role,
            source=source,
            staff_email=staff_email,
        )
        if current:
            return current

    existing = get_assignments_by_external_ids([ext_id], source=source).get(ext_id)
    if existing:
        return existing

    if not crm_available():
        raise RuntimeError("CRM database not configured")

    now = _now_iso()
    row: dict[str, Any] = {
        "source": source,
        "external_id": ext_id,
        "status": STATUS_ASSIGNED,
        "snapshot": {},
        "assigned_at": now,
        "updated_at": now,
    }
    if staff_user_id and staff_role:
        row[_staff_column_for_role(staff_role)] = staff_user_id

    result = (
        _client()
        .table("lead_assignments")
        .upsert(row, on_conflict="source,external_id")
        .select("*")
        .execute()
    )
    data = (result.data or [None])[0]
    if not data:
        raise RuntimeError("Failed to initialize lead progress")
    return data


def _update_assignment_snapshot(
    *,
    external_id: str,
    source: str,
    snapshot: dict[str, Any],
) -> dict[str, Any]:
    now = _now_iso()
    update = {"snapshot": snapshot, "updated_at": now}
    result = (
        _client()
        .table("lead_assignments")
        .update(update)
        .eq("source", source)
        .eq("external_id", external_id)
        .select("*")
        .execute()
    )
    data = (result.data or [None])[0]
    if not data:
        raise RuntimeError("Lead assignment not found")
    return format_my_lead_row(data)


def add_custom_progress_stage(
    *,
    external_id: str,
    source: str,
    title: str,
    description: str | None = None,
    insert_after: str = STATUS_ASSIGNED,
    author_name: str | None = None,
    staff_user_id: str | None = None,
    staff_role: str | None = None,
    staff_email: str | None = None,
) -> dict[str, Any]:
    stage_title = (title or "").strip()
    if not stage_title:
        raise ValueError("Stage title is required")

    anchor_raw = (insert_after or STATUS_ASSIGNED).strip()
    anchor_lower = anchor_raw.lower()

    current = get_or_create_assignment_for_progress(
        external_id=external_id,
        source=source,
        staff_user_id=staff_user_id,
        staff_role=staff_role,
        staff_email=staff_email,
    )
    snap = current.get("snapshot") if isinstance(current.get("snapshot"), dict) else {}
    stages = progress_stages_from_assignment(current)
    known_ids = {str(s.get("id") or "") for s in stages if s.get("id")}

    if anchor_lower in VALID_PROGRESS_ANCHORS:
        anchor = anchor_lower
    elif anchor_raw in known_ids:
        anchor = anchor_raw
    else:
        raise ValueError("Invalid insert position")
    now = _now_iso()
    stages.append({
        "id": str(uuid.uuid4()),
        "title": stage_title,
        "description": (description or "").strip() or None,
        "insert_after": anchor,
        "completed_at": None,
        "created_at": now,
        "created_by_name": (author_name or "").strip() or None,
    })
    next_snapshot = _snapshot_with_progress_stages(snap, stages)
    log = comment_log_from_assignment(current)
    if log:
        next_snapshot = _snapshot_with_comment_log(next_snapshot, log)
    return _update_assignment_snapshot(
        external_id=external_id,
        source=source,
        snapshot=next_snapshot,
    )


def complete_custom_progress_stage(
    *,
    external_id: str,
    source: str,
    stage_id: str,
    staff_user_id: str | None = None,
    staff_role: str | None = None,
    staff_email: str | None = None,
) -> dict[str, Any]:
    stage_key = (stage_id or "").strip()
    if not stage_key:
        raise ValueError("Missing stage id")

    current = get_or_create_assignment_for_progress(
        external_id=external_id,
        source=source,
        staff_user_id=staff_user_id,
        staff_role=staff_role,
        staff_email=staff_email,
    )
    snap = current.get("snapshot") if isinstance(current.get("snapshot"), dict) else {}
    stages = progress_stages_from_assignment(current)
    found = False
    now = _now_iso()
    for stage in stages:
        if stage.get("id") == stage_key:
            stage["completed_at"] = now
            found = True
            break
    if not found:
        raise ValueError("Stage not found")

    next_snapshot = _snapshot_with_progress_stages(snap, stages)
    log = comment_log_from_assignment(current)
    if log:
        next_snapshot = _snapshot_with_comment_log(next_snapshot, log)
    return _update_assignment_snapshot(
        external_id=external_id,
        source=source,
        snapshot=next_snapshot,
    )


def format_my_lead_row(row: dict[str, Any]) -> dict[str, Any]:
    out = dict(row)
    out["comment_log"] = comment_log_from_assignment(row)
    out["custom_progress_stages"] = progress_stages_from_assignment(row)
    return out


def _tatva_employee_email_from_assignment(assignment: dict[str, Any]) -> str:
    snap = assignment.get("snapshot") if isinstance(assignment.get("snapshot"), dict) else {}
    te = snap.get("tatva_employee") if isinstance(snap.get("tatva_employee"), dict) else {}
    return str(te.get("email") or "").strip().lower()


def _is_tatva_assignee_id(value: Any) -> bool:
    return str(value or "").startswith(TATVA_EMPLOYEE_PREFIX)


def get_assignment_for_staff(
    *,
    external_id: str,
    staff_user_id: str,
    staff_role: str,
    source: str,
    staff_email: str | None = None,
) -> dict[str, Any] | None:
    """Find a lead assignment owned by this CRM user or linked Tatva employee."""
    col = _staff_column_for_role(staff_role)
    client = _client()
    direct = (
        client.table("lead_assignments")
        .select("*")
        .eq("source", source)
        .eq("external_id", external_id)
        .eq(col, staff_user_id)
        .execute()
    )
    if direct.data:
        return direct.data[0]

    email = (staff_email or "").strip().lower()
    if not email:
        return None

    tatva_rows = (
        client.table("lead_assignments")
        .select("*")
        .eq("source", source)
        .eq("external_id", external_id)
        .execute()
    )
    for row in tatva_rows.data or []:
        if not _is_tatva_assignee_id(row.get(col)):
            continue
        if _tatva_employee_email_from_assignment(row) == email:
            return row
    return None


def _list_tatva_assignments_for_email(
    *,
    staff_email: str,
    staff_role: str,
    source: str,
    status: str | None,
) -> list[dict[str, Any]]:
    email = staff_email.strip().lower()
    if not email:
        return []
    col = _staff_column_for_role(staff_role)
    result = (
        _client()
        .table("lead_assignments")
        .select("*")
        .eq("source", source)
        .execute()
    )
    rows: list[dict[str, Any]] = []
    for row in result.data or []:
        if not _is_tatva_assignee_id(row.get(col)):
            continue
        if _tatva_employee_email_from_assignment(row) != email:
            continue
        if status and row.get("status") != status:
            continue
        rows.append(row)
    return rows


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
    existing = get_assignments_by_external_ids([external_id], source=source).get(external_id) or {}
    merged_snapshot = dict(snapshot)
    if existing:
        old_snap = existing.get("snapshot") if isinstance(existing.get("snapshot"), dict) else {}
        old_log = old_snap.get(TEAM_COMMENT_LOG_KEY)
        if isinstance(old_log, list) and old_log:
            merged_snapshot[TEAM_COMMENT_LOG_KEY] = old_log
    row: dict[str, Any] = {
        "source": source,
        "external_id": external_id,
        "status": STATUS_ASSIGNED,
        "snapshot": merged_snapshot,
        "assigned_at": now,
        "updated_at": now,
        col: staff_user_id,
    }
    if existing.get("notes"):
        row["notes"] = existing["notes"]
    existing_log = comment_log_from_assignment(existing)
    if existing_log:
        row["snapshot"] = _snapshot_with_comment_log(merged_snapshot, existing_log)
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
    staff_email: str | None = None,
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

    merged_rows: dict[str, dict[str, Any]] = {
        str(row.get("external_id")): row for row in (result.data or [])
    }
    for row in _list_tatva_assignments_for_email(
        staff_email=staff_email or "",
        staff_role=staff_role,
        source=source,
        status=status,
    ):
        ext = str(row.get("external_id") or "")
        if ext and ext not in merged_rows:
            merged_rows[ext] = row

    all_rows = sorted(
        merged_rows.values(),
        key=lambda r: str(r.get("assigned_at") or ""),
        reverse=True,
    )
    total = len(all_rows)
    page_rows = all_rows[offset: offset + limit]
    items = [format_my_lead_row(row) for row in page_rows]
    total_pages = max(1, (total + limit - 1) // limit) if total else 1
    return {
        "items": items,
        "total": total,
        "page": page,
        "limit": limit,
        "totalPages": total_pages,
    }


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        raw = str(value).replace("Z", "+00:00")
        dt = datetime.fromisoformat(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except ValueError:
        return None


def period_bounds(period: str) -> tuple[datetime | None, datetime | None]:
    """Return UTC start/end for dashboard period filters."""
    now = datetime.now(timezone.utc)
    key = (period or "month").strip().lower().replace("-", "_")
    if key == "all":
        return None, None
    if key == "day":
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        return start, now
    if key == "month":
        start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        return start, now
    if key == "quarter":
        quarter_start = ((now.month - 1) // 3) * 3 + 1
        start = now.replace(month=quarter_start, day=1, hour=0, minute=0, second=0, microsecond=0)
        return start, now
    if key in {"half_year", "bi_annually", "biannually"}:
        start_month = 1 if now.month <= 6 else 7
        start = now.replace(month=start_month, day=1, hour=0, minute=0, second=0, microsecond=0)
        return start, now
    if key == "year":
        start = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
        return start, now
    start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return start, now


def _dt_in_range(dt: datetime | None, start: datetime | None, end: datetime | None) -> bool:
    if dt is None:
        return False
    if start and dt < start:
        return False
    if end and dt > end:
        return False
    return True


def _lead_bucket_stats(
    rows: list[dict[str, Any]],
    start: datetime | None,
    end: datetime | None,
) -> dict[str, Any]:
    if start is None and end is None:
        filtered = rows
    else:
        filtered = [
            row for row in rows
            if _dt_in_range(_parse_dt(str(row.get("assigned_at") or "")), start, end)
        ]
    total = len(filtered)
    completed = sum(
        1 for row in filtered
        if str(row.get("status") or "") == STATUS_PRESALES_COMPLETED
    )
    pending = total - completed
    achievement_pct = round((completed / total) * 100, 1) if total else 0.0
    return {
        "total": total,
        "pending": pending,
        "completed": completed,
        "achievement_pct": achievement_pct,
    }


def _all_assignments_for_staff(
    *,
    staff_user_id: str,
    staff_role: str,
    source: str,
    staff_email: str | None = None,
) -> list[dict[str, Any]]:
    col = _staff_column_for_role(staff_role)
    result = (
        _client()
        .table("lead_assignments")
        .select("*")
        .eq("source", source)
        .eq(col, staff_user_id)
        .execute()
    )
    merged: dict[str, dict[str, Any]] = {
        str(row.get("external_id")): row for row in (result.data or [])
    }
    for row in _list_tatva_assignments_for_email(
        staff_email=staff_email or "",
        staff_role=staff_role,
        source=source,
        status=None,
    ):
        ext = str(row.get("external_id") or "")
        if ext and ext not in merged:
            merged[ext] = row
    return list(merged.values())


def my_leads_dashboard(
    *,
    staff_user_id: str,
    staff_role: str,
    staff_email: str | None = None,
    period: str = "month",
) -> dict[str, Any]:
    start, end = period_bounds(period)
    user_rows = _all_assignments_for_staff(
        staff_user_id=staff_user_id,
        staff_role=staff_role,
        source=SOURCE_TATVA_PRESALES,
        staff_email=staff_email,
    )
    vendor_rows = _all_assignments_for_staff(
        staff_user_id=staff_user_id,
        staff_role=staff_role,
        source=SOURCE_TATVA_VENDOR,
        staff_email=staff_email,
    )
    user_stats = _lead_bucket_stats(user_rows, start, end)
    vendor_stats = _lead_bucket_stats(vendor_rows, start, end)
    overall_total = user_stats["total"] + vendor_stats["total"]
    overall_completed = user_stats["completed"] + vendor_stats["completed"]
    overall_pending = user_stats["pending"] + vendor_stats["pending"]
    return {
        "period": period,
        "period_start": start.isoformat() if start else None,
        "period_end": end.isoformat() if end else None,
        "user_leads": user_stats,
        "vendor_leads": vendor_stats,
        "overall": {
            "total": overall_total,
            "pending": overall_pending,
            "completed": overall_completed,
            "achievement_pct": round((overall_completed / overall_total) * 100, 1) if overall_total else 0.0,
        },
        "generated_at": _now_iso(),
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
    author_id: str | None = None,
    author_name: str | None = None,
    staff_email: str | None = None,
) -> dict[str, Any]:
    text = (notes or "").strip()
    if not text:
        raise ValueError("Comment cannot be empty")

    col = _staff_column_for_role(staff_role)
    now = _now_iso()
    current = get_assignment_for_staff(
        external_id=external_id,
        staff_user_id=staff_user_id,
        staff_role=staff_role,
        source=source,
        staff_email=staff_email,
    )
    if not current:
        raise RuntimeError("Lead not found or not assigned to you")

    assignee_id = current.get(col)
    log = comment_log_from_assignment(current)
    log.append({
        "text": text,
        "created_at": now,
        "author_id": author_id,
        "author_name": (author_name or "").strip() or None,
    })

    snap = current.get("snapshot") if isinstance(current.get("snapshot"), dict) else {}
    update: dict[str, Any] = {
        "notes": text,
        "snapshot": _snapshot_with_comment_log(snap, log),
        "updated_at": now,
    }
    result = (
        _client()
        .table("lead_assignments")
        .update(update)
        .eq("source", source)
        .eq("external_id", external_id)
        .eq(col, assignee_id)
        .select("*")
        .execute()
    )
    data = (result.data or [None])[0]
    if not data:
        data = {**current, **update}
    return format_my_lead_row(data)


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


def assign_presales_vendor(
    *,
    external_id: str,
    vendor_id: str,
    vendor_name: str = "",
    vendor_company: str = "",
    vendor_phone: str = "",
    snapshot: dict[str, Any],
    source: str = SOURCE_TATVA_PRESALES_VENDOR,
) -> dict[str, Any]:
    """Link an approved Tatva vendor to a presales lead."""
    full_snapshot = {
        **snapshot,
        "tatva_vendor": {
            "id": vendor_id,
            "name": vendor_name,
            "company": vendor_company,
            "phone": vendor_phone,
        },
    }
    now = _now_iso()
    row: dict[str, Any] = {
        "source": source,
        "external_id": external_id,
        "status": STATUS_ASSIGNED,
        "snapshot": full_snapshot,
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
        raise RuntimeError("Failed to assign vendor")
    return data


def _vendor_from_snapshot(assignment: dict[str, Any]) -> dict[str, str]:
    snap = assignment.get("snapshot") or {}
    tv = snap.get("tatva_vendor") if isinstance(snap, dict) else None
    if not isinstance(tv, dict):
        return {}
    return {
        "id": str(tv.get("id") or "").strip(),
        "name": str(tv.get("name") or "").strip(),
        "company": str(tv.get("company") or "").strip(),
        "phone": str(tv.get("phone") or "").strip(),
    }


def _vendor_assignment_meta(assignment: dict[str, Any]) -> dict[str, Any]:
    vendor = _vendor_from_snapshot(assignment)
    name = vendor.get("name") or vendor.get("company") or ""
    if vendor.get("name") and vendor.get("company") and vendor["name"] != vendor["company"]:
        display = f"{vendor['name']} ({vendor['company']})"
    else:
        display = name
    return {
        "status": assignment.get("status") or STATUS_UNASSIGNED,
        "vendor_id": vendor.get("id") or None,
        "vendor_name": display or None,
        "assigned_at": assignment.get("assigned_at"),
        "notes": assignment.get("notes"),
        "comment_log": comment_log_from_assignment(assignment),
        "custom_progress_stages": progress_stages_from_assignment(assignment),
    }


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
        "presales_completed_at": assignment.get("presales_completed_at"),
        "notes": assignment.get("notes"),
        "comment_log": comment_log_from_assignment(assignment),
        "custom_progress_stages": progress_stages_from_assignment(assignment),
    }


def enrich_presales_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Merge Tatva presales rows with Supabase assignment metadata."""
    if not items:
        return []
    ids = [str(i.get("_id") or "") for i in items if i.get("_id")]
    assignments = get_assignments_by_external_ids(ids)
    vendor_assignments = get_assignments_by_external_ids(
        ids,
        source=SOURCE_TATVA_PRESALES_VENDOR,
    )
    users_by_id = {u["id"]: u for u in list_crm_users(active_only=True)}
    enriched: list[dict[str, Any]] = []
    for item in items:
        ext_id = str(item.get("_id") or "")
        assignment = assignments.get(ext_id) or {}
        vendor_assignment = vendor_assignments.get(ext_id) or {}
        enriched.append({
            **item,
            "assignment": _assignment_meta(assignment, users_by_id),
            "vendor_assignment": _vendor_assignment_meta(vendor_assignment),
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

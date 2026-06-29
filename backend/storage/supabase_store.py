"""
Supabase persistence for enquiries, summaries, session logs, and attachments.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from backend.integrations.tatva_enquiry_submit import _normalize_attachments
from backend.storage.supabase_client import get_supabase_client, is_supabase_configured


def is_configured() -> bool:
    return is_supabase_configured()


def _client():
    client = get_supabase_client()
    if client is None:
        return None
    return client


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _enriched_fields(session, *, status: str | None = None) -> dict[str, Any]:
    from backend.admin.enquiry_display import snapshot_requirements_for_session

    fields = snapshot_requirements_for_session(session)
    tatva_summary = session.flow_state.get("tatva_enquiry_summary")
    if isinstance(tatva_summary, dict) and tatva_summary:
        fields["tatva_enquiry_summary"] = tatva_summary
    tatva_id = session.flow_state.get("tatva_enquiry_id")
    if tatva_id:
        fields["tatva_enquiry_id"] = str(tatva_id)
    file_records = _all_enquiry_attachment_records(session)
    if file_records:
        fields["_enquiry_files"] = file_records
        fields["_enquiry_attachment_urls"] = [
            str(item.get("file_url") or "").strip()
            for item in file_records
            if str(item.get("file_url") or "").strip()
        ]
    if status:
        fields["_enquiry_status"] = status
    return fields


def _records_from_tatva_list(raw: Any) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in _normalize_attachments(raw if isinstance(raw, list) else None):
        url = item["url"]
        name = str(item.get("key") or "").strip()
        if name:
            name = name.rsplit("/", 1)[-1]
        rows.append({
            "file_name": name or "Uploaded file",
            "file_url": url,
            "mime_type": str(item.get("mime") or ""),
        })
    return rows


def _tatva_enquiry_attachment_records(session) -> list[dict[str, Any]]:
    """Files returned by Tatva for this submitted enquiry only."""
    return _records_from_tatva_list(session.flow_state.get("tatva_enquiry_attachments"))


def _all_enquiry_attachment_records(session) -> list[dict[str, Any]]:
    """Merge WhatsApp session uploads and Tatva enquiry attachment URLs."""
    seen: set[str] = set()
    rows: list[dict[str, Any]] = []

    for meta in _session_upload_attachments(session):
        url = str(meta.file_url or "").strip()
        if not url or url in seen:
            continue
        seen.add(url)
        uploaded = meta.uploaded_at
        rows.append({
            "file_name": str(meta.file_name or "Uploaded file"),
            "file_url": url,
            "mime_type": str(meta.mime_type or ""),
            "uploaded_at": uploaded.isoformat() if hasattr(uploaded, "isoformat") else _now_iso(),
        })

    for item in _tatva_enquiry_attachment_records(session):
        url = str(item.get("file_url") or "").strip()
        if not url or url in seen:
            continue
        seen.add(url)
        rows.append(item)

    return rows


def _stored_file_records(fields: dict[str, Any]) -> list[dict[str, Any]]:
    stored = fields.get("_enquiry_files")
    if not isinstance(stored, list):
        return []
    return [
        item for item in stored
        if isinstance(item, dict) and str(item.get("file_url") or "").strip()
    ]


def _flow_state_attachment_records(session_id: str) -> list[dict[str, Any]]:
    """Recover Tatva file URLs from sessions_log when enquiry row predates file persistence."""
    client = _client()
    if client is None or not session_id:
        return []
    result = (
        client.table("sessions_log")
        .select("flow_state")
        .eq("session_id", session_id)
        .limit(1)
        .execute()
    )
    rows = result.data or []
    if not rows:
        return []
    flow_state = rows[0].get("flow_state") or {}
    if not isinstance(flow_state, dict):
        return []
    return _records_from_tatva_list(flow_state.get("tatva_enquiry_attachments"))


def _resolve_enquiry_attachments(
    session_id: str,
    fields: dict[str, Any],
    db_attachments: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Prefer stored enquiry files; fall back to DB rows or sessions_log."""
    stored = _stored_file_records(fields)
    if stored:
        return stored

    filtered = _filter_stored_attachments(db_attachments, fields)
    if filtered:
        return filtered

    recovered = _flow_state_attachment_records(session_id)
    if recovered:
        return recovered

    return []


def _session_upload_attachments(session) -> list:
    """Files uploaded in this WhatsApp enquiry only ΓÇö not Tatva account history."""
    seen: set[str] = set()
    unique = []
    for meta in session.attachments or []:
        url = str(meta.file_url or "").strip()
        if not url or url in seen:
            continue
        seen.add(url)
        unique.append(meta)
    return unique


def _filter_stored_attachments(
    attachments: list[dict[str, Any]],
    fields: dict[str, Any],
) -> list[dict[str, Any]]:
    """Keep only files belonging to this enquiry's upload step."""
    allowed = fields.get("_enquiry_attachment_urls")
    if isinstance(allowed, list) and allowed:
        allowed_set = {str(u).strip() for u in allowed if str(u).strip()}
        return [a for a in attachments if str(a.get("file_url") or "").strip() in allowed_set]

    # Legacy rows: WhatsApp uploads are stored as twilio:ΓÇª refs ΓÇö exclude Tatva CDN bulk.
    whatsapp_uploads = [
        a for a in attachments
        if str(a.get("file_url") or "").startswith("twilio:")
    ]
    if whatsapp_uploads:
        return whatsapp_uploads
    if len(attachments) <= 5:
        return attachments
    return []


def _attachment_rows(session_id: str, session) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in _all_enquiry_attachment_records(session):
        rows.append({
            "session_id": session_id,
            "file_name": str(item.get("file_name") or "Uploaded file"),
            "file_url": str(item.get("file_url") or ""),
            "mime_type": str(item.get("mime_type") or ""),
            "uploaded_at": item.get("uploaded_at") or _now_iso(),
        })
    return rows


def _replace_attachments(session_id: str, session) -> None:
    client = _client()
    if client is None:
        return
    client.table("enquiry_attachments").delete().eq("session_id", session_id).execute()
    rows = _attachment_rows(session_id, session)
    if rows:
        client.table("enquiry_attachments").insert(rows).execute()


def _upsert_enquiry_row(session, *, status: str, save_attachments: bool) -> bool:
    client = _client()
    if client is None:
        return False

    row = {
        "session_id": session.session_id,
        "phone_number": session.phone_number,
        "channel": session.channel,
        "extracted_fields": _enriched_fields(session, status=status),
        "completed_fields": list(session.completed_fields or []),
        "service_category": session.service_category.value if session.service_category else None,
        "lead_score": session.lead_score,
        "lead_tier": session.lead_tier,
        "updated_at": _now_iso(),
    }
    client.table("enquiries").upsert(row, on_conflict="session_id").execute()
    if save_attachments:
        _replace_attachments(session.session_id, session)
    return True


async def save_enquiry(session) -> bool:
    status = "declined" if session.flow_state.get("project_declined") else "in_progress"
    if session.summary_generated:
        status = "completed"
    has_files = bool(_all_enquiry_attachment_records(session))
    return _upsert_enquiry_row(session, status=status, save_attachments=has_files)


async def persist_terminal_enquiry(session) -> bool:
    status = "declined" if session.flow_state.get("project_declined") else "completed"
    has_files = bool(_all_enquiry_attachment_records(session))
    return _upsert_enquiry_row(session, status=status, save_attachments=has_files)


async def save_summary(summary, phone_number: str = "") -> bool:
    client = _client()
    if client is None:
        return False

    data = summary.model_dump(mode="json") if hasattr(summary, "model_dump") else dict(summary)
    row = {
        "session_id": data.get("session_id") or "",
        "phone_number": phone_number,
        "service_category": data.get("service_category"),
        "next_step": data.get("next_step"),
        "project_overview": data.get("project_overview"),
        "scope_of_work": data.get("scope_of_work") or [],
        "client_requirements": data.get("client_requirements"),
        "technical_specs": data.get("technical_specs"),
        "timeline": data.get("timeline"),
        "special_considerations": data.get("special_considerations"),
        "estimated_scope": data.get("estimated_scope"),
        "design_direction": data.get("design_direction"),
        "execution_readiness": data.get("execution_readiness"),
        "enquiry_snapshot": data.get("enquiry_snapshot") or {},
        "generated_at": data.get("generated_at") or _now_iso(),
    }
    if not row["session_id"]:
        return False
    client.table("project_summaries").insert(row).execute()
    return True


async def upsert_session_log(session) -> bool:
    client = _client()
    if client is None:
        return False

    row = {
        "session_id": session.session_id,
        "phone_number": session.phone_number,
        "channel": session.channel,
        "conversation_stage": session.conversation_stage.value if session.conversation_stage else None,
        "field_completion_pct": session.field_completion_pct,
        "turn_count": session.turn_count,
        "service_category": session.service_category.value if session.service_category else None,
        "active_consultant": session.active_consultant,
        "lead_score": session.lead_score,
        "lead_tier": session.lead_tier,
        "flow_state": session.flow_state or {},
        "last_active": session.last_active.isoformat() if session.last_active else _now_iso(),
    }
    client.table("sessions_log").upsert(row, on_conflict="session_id").execute()

    if session.extracted_fields:
        status = "declined" if session.flow_state.get("project_declined") else "in_progress"
        if session.summary_generated:
            status = "completed"
        _upsert_enquiry_row(session, status=status, save_attachments=False)

    return True


def _attachments_for_sessions(session_ids: list[str]) -> dict[str, list[dict[str, Any]]]:
    client = _client()
    if client is None or not session_ids:
        return {}
    result = (
        client.table("enquiry_attachments")
        .select("session_id,file_name,file_url,mime_type,uploaded_at")
        .in_("session_id", session_ids)
        .execute()
    )
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in result.data or []:
        sid = str(row.get("session_id") or "")
        grouped.setdefault(sid, []).append(row)
    return grouped


async def get_all_enquiries() -> list[dict]:
    client = _client()
    if client is None:
        return []

    result = (
        client.table("enquiries")
        .select("*")
        .order("updated_at", desc=True)
        .execute()
    )
    rows = list(result.data or [])
    if not rows:
        return []

    session_ids = [str(r.get("session_id") or "") for r in rows if r.get("session_id")]
    attachments_by_session = _attachments_for_sessions(session_ids)

    enquiries: list[dict] = []
    for row in rows:
        sid = str(row.get("session_id") or "")
        fields = row.get("extracted_fields") or {}
        status = str(fields.get("_enquiry_status") or "completed")
        raw_attachments = attachments_by_session.get(sid, [])
        resolved = _resolve_enquiry_attachments(sid, fields, raw_attachments)
        enquiries.append({
            "id": row.get("id"),
            "session_id": sid,
            "phone_number": row.get("phone_number"),
            "channel": row.get("channel"),
            "service_category": row.get("service_category"),
            "extracted_fields": fields,
            "completed_fields": row.get("completed_fields") or [],
            "completion_pct": _completion_pct(row),
            "lead_score": row.get("lead_score"),
            "lead_tier": row.get("lead_tier"),
            "status": status,
            "attachment_count": len(resolved),
            "attachments": resolved,
            "created_at": row.get("created_at"),
            "last_active": row.get("updated_at") or row.get("created_at"),
            "source": "supabase",
        })
    return enquiries


def _completion_pct(row: dict) -> int:
    completed = row.get("completed_fields") or []
    fields = row.get("extracted_fields") or {}
    if not fields:
        return 0
    total = max(len(fields), len(completed), 1)
    return min(100, int(len(completed) / total * 100))


async def get_latest_enquiry_profile_by_phone(phone_number: str) -> dict[str, str]:
    client = _client()
    if client is None:
        return {}
    needle = (phone_number or "").replace("whatsapp:", "").strip()
    if not needle:
        return {}
    result = (
        client.table("enquiries")
        .select("extracted_fields,phone_number")
        .or_(f"phone_number.eq.{needle},phone_number.eq.whatsapp:{needle}")
        .order("updated_at", desc=True)
        .limit(1)
        .execute()
    )
    rows = result.data or []
    if not rows:
        return {}
    ef = rows[0].get("extracted_fields") or {}
    return {k: str(v) for k, v in ef.items() if v is not None and str(v).strip()}


async def get_all_summaries() -> list[dict]:
    client = _client()
    if client is None:
        return []
    result = client.table("project_summaries").select("*").order("generated_at", desc=True).execute()
    return list(result.data or [])


async def save_attachment_record(
    session_id: str,
    file_name: str,
    file_url: str,
    mime_type: str = "",
) -> bool:
    client = _client()
    if client is None:
        return False
    client.table("enquiry_attachments").insert({
        "session_id": session_id,
        "file_name": file_name,
        "file_url": file_url,
        "mime_type": mime_type,
        "uploaded_at": _now_iso(),
    }).execute()
    return True


async def get_all_attachments(session_id: str | None = None) -> list[dict]:
    client = _client()
    if client is None:
        return []
    query = client.table("enquiry_attachments").select("*")
    if session_id:
        query = query.eq("session_id", session_id)
    result = query.order("uploaded_at", desc=True).execute()
    return list(result.data or [])

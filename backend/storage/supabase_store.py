"""
Aadhya – Supabase Persistent Storage
Stores enquiries and project summaries to Supabase PostgreSQL.
"""
from __future__ import annotations
from datetime import datetime
from typing import Any
from backend.config import get_settings

settings = get_settings()

_client = None


def _get_client():
    global _client
    if _client is None and settings.supabase_url and settings.supabase_service_key:
        try:
            from supabase import create_client
            _client = create_client(settings.supabase_url, settings.supabase_service_key)
        except Exception:
            _client = None
    return _client


def is_configured() -> bool:
    return bool(
        settings.supabase_url
        and settings.supabase_service_key
        and settings.supabase_url != "https://your-project.supabase.co"
    )


# ─── SQL to create tables (run once in Supabase) ─────────────────────────────
SCHEMA_SQL = """
-- Enquiries Table
CREATE TABLE IF NOT EXISTS enquiries (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    session_id TEXT NOT NULL,
    phone_number TEXT,
    channel TEXT,
    extracted_fields JSONB,
    completed_fields JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Project Summaries Table
CREATE TABLE IF NOT EXISTS project_summaries (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    session_id TEXT NOT NULL,
    phone_number TEXT,
    next_step TEXT,
    project_overview TEXT,
    scope_of_work JSONB,
    client_requirements TEXT,
    technical_specs TEXT,
    timeline TEXT,
    special_considerations TEXT,
    estimated_scope TEXT,
    design_direction TEXT,
    execution_readiness TEXT,
    enquiry_snapshot JSONB,
    generated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Sessions Log Table
CREATE TABLE IF NOT EXISTS sessions_log (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    session_id TEXT UNIQUE NOT NULL,
    phone_number TEXT,
    channel TEXT,
    conversation_stage TEXT,
    field_completion_pct INTEGER,
    turn_count INTEGER,
    service_category TEXT,
    active_consultant TEXT,
    lead_score INTEGER,
    lead_tier TEXT,
    flow_state JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    last_active TIMESTAMPTZ DEFAULT NOW()
);

-- Enquiry attachments (WhatsApp uploads)
CREATE TABLE IF NOT EXISTS enquiry_attachments (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    session_id TEXT NOT NULL,
    file_name TEXT,
    file_url TEXT,
    mime_type TEXT,
    uploaded_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS enquiries_session_id_idx ON enquiries (session_id);
"""

# ─── CRUD operations ─────────────────────────────────────────────────────────

async def save_enquiry(session) -> bool:
    """Save or upsert enquiry data from a session."""
    if not is_configured():
        return False
    try:
        client = _get_client()
        record = {
            "session_id": session.session_id,
            "phone_number": session.phone_number,
            "channel": session.channel,
            "extracted_fields": session.extracted_fields,
            "completed_fields": session.completed_fields,
            "service_category": session.service_category.value if session.service_category else None,
            "lead_score": session.lead_score,
            "lead_tier": session.lead_tier,
            "updated_at": datetime.utcnow().isoformat(),
        }
        client.table("enquiries").upsert(record, on_conflict="session_id").execute()
        return True
    except Exception as e:
        print(f"[Supabase] save_enquiry error: {e}")
        return False


async def persist_terminal_enquiry(session) -> bool:
    """Persist enquiry when the client submitted or declined to start a project."""
    if session.flow_state.get("project_declined"):
        return await save_enquiry(session)
    if session.summary_generated and session.summary:
        return await save_enquiry(session)
    return False


async def save_summary(summary, phone_number: str = "") -> bool:
    """Insert a generated project summary."""
    if not is_configured():
        return False
    try:
        client = _get_client()
        sc = getattr(summary, "service_category", None)
        record = {
            "session_id": summary.session_id,
            "phone_number": phone_number,
            "service_category": sc,
            "next_step": summary.next_step,
            "project_overview": summary.project_overview,
            "scope_of_work": summary.scope_of_work,
            "client_requirements": summary.client_requirements,
            "technical_specs": summary.technical_specs,
            "timeline": summary.timeline,
            "special_considerations": summary.special_considerations,
            "estimated_scope": summary.estimated_scope,
            "design_direction": summary.design_direction,
            "execution_readiness": summary.execution_readiness,
            "enquiry_snapshot": summary.enquiry_snapshot,
            "generated_at": summary.generated_at.isoformat(),
        }
        client.table("project_summaries").insert(record).execute()
        return True
    except Exception as e:
        print(f"[Supabase] save_summary error: {e}")
        return False


async def upsert_session_log(session) -> bool:
    """Update the sessions_log table with current session state."""
    if not is_configured():
        return False
    try:
        client = _get_client()
        record = {
            "session_id": session.session_id,
            "phone_number": session.phone_number,
            "channel": session.channel,
            "conversation_stage": session.conversation_stage.value,
            "field_completion_pct": session.field_completion_pct,
            "turn_count": session.turn_count,
            "service_category": session.service_category.value if session.service_category else None,
            "active_consultant": session.active_consultant,
            "lead_score": session.lead_score,
            "lead_tier": session.lead_tier,
            "flow_state": session.flow_state,
            "last_active": session.last_active.isoformat(),
        }
        client.table("sessions_log").upsert(record, on_conflict="session_id").execute()
        return True
    except Exception as e:
        print(f"[Supabase] upsert_session_log error: {e}")
        return False


async def get_all_enquiries() -> list[dict]:
    if not is_configured():
        return []
    try:
        client = _get_client()
        result = client.table("enquiries").select("*").order("updated_at", desc=True).execute()
        return result.data or []
    except Exception:
        return []


def _phone_lookup_variants(phone_number: str) -> list[str]:
    """Normalize WhatsApp/E.164 phone values for enquiry lookup."""
    from backend.integrations.tatva_users import normalize_phone_for_tatva

    raw = (phone_number or "").strip()
    if not raw:
        return []
    digits = normalize_phone_for_tatva(raw)
    variants: list[str] = []
    for candidate in (raw, f"whatsapp:+91{digits}", f"whatsapp:{digits}", f"+91{digits}", digits):
        if candidate and candidate not in variants:
            variants.append(candidate)
    return variants


async def get_latest_enquiry_profile_by_phone(phone_number: str) -> dict[str, str]:
    """Most recent enquiry profile fields for a returning user (name, city, location)."""
    if not is_configured():
        return {}
    variants = _phone_lookup_variants(phone_number)
    if not variants:
        return {}
    try:
        client = _get_client()
        result = (
            client.table("enquiries")
            .select("extracted_fields,phone_number,updated_at")
            .in_("phone_number", variants)
            .order("updated_at", desc=True)
            .limit(1)
            .execute()
        )
        rows = result.data or []
        if not rows:
            return {}
        extracted = rows[0].get("extracted_fields") or {}
        profile: dict[str, str] = {}
        for key in ("client_name", "city", "property_location", "email", "preferred_contact_time"):
            value = str(extracted.get(key) or "").strip()
            if value:
                profile[key] = value
        return profile
    except Exception as e:
        print(f"[Supabase] get_latest_enquiry_profile_by_phone error: {e}")
        return {}


async def get_all_summaries() -> list[dict]:
    if not is_configured():
        return []
    try:
        client = _get_client()
        result = client.table("project_summaries").select("*").order("generated_at", desc=True).execute()
        return result.data or []
    except Exception:
        return []


async def save_attachment_record(
    session_id: str,
    file_name: str,
    file_url: str,
    mime_type: str = "",
) -> bool:
    if not is_configured():
        return False
    try:
        client = _get_client()
        client.table("enquiry_attachments").insert({
            "session_id": session_id,
            "file_name": file_name,
            "file_url": file_url,
            "mime_type": mime_type,
            "uploaded_at": datetime.utcnow().isoformat(),
        }).execute()
        return True
    except Exception as e:
        print(f"[Supabase] save_attachment_record error: {e}")
        return False


async def get_all_attachments(session_id: str | None = None) -> list[dict]:
    if not is_configured():
        return []
    try:
        client = _get_client()
        q = client.table("enquiry_attachments").select("*")
        if session_id:
            q = q.eq("session_id", session_id)
        result = q.order("uploaded_at", desc=True).execute()
        return result.data or []
    except Exception:
        return []

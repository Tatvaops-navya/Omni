"""
Aadhya – Admin API Router
All endpoints backing the /krsna admin panel.
Protected by require_admin dependency.
"""
from __future__ import annotations
import asyncio
import json
from datetime import datetime
from typing import Any, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from backend.admin.auth import require_admin, require_admin_sse, require_staff, generate_session_token
from backend.config import get_settings
from backend.storage import supabase_store
from backend.storage.redis_store import get_session, delete_session, list_all_sessions
from backend.utils.logger import get_recent_logs
from backend.schemas.session import ConversationStage

settings = get_settings()
router = APIRouter(prefix="/admin", tags=["admin"])

# ─── Auth endpoint (no protection — it IS the login) ─────────────────────────

class LoginRequest(BaseModel):
    password: str


@router.post("/login")
async def admin_login(body: LoginRequest):
    """Exchange admin password for a session token."""
    if body.password != settings.admin_password:
        raise HTTPException(status_code=401, detail="Invalid password")
    token = generate_session_token(role="admin", name="Admin")
    return {
        "token": token,
        "expires_in_hours": 8,
        "user": {"role": "admin", "name": "Admin", "email": None, "id": None},
    }


# ─── Dashboard ────────────────────────────────────────────────────────────────

@router.get("/dashboard")
async def get_dashboard(auth=Depends(require_admin)):
    sessions = await list_all_sessions()
    now = datetime.utcnow()

    active = [s for s in sessions if s.conversation_stage != ConversationStage.SUMMARY_GENERATED]
    completed = [
        s for s in sessions
        if s.summary_generated or s.flow_state.get("project_declined")
    ]

    whatsapp_today = sum(1 for s in sessions if s.channel == "whatsapp")
    voice_today = sum(1 for s in sessions if s.channel == "voice")

    # Hourly message distribution (last 24h, from logs)
    logs = get_recent_logs(500)
    hourly = {}
    for entry in logs:
        if entry.get("event") == "USER_MESSAGE":
            try:
                ts = datetime.fromisoformat(entry["timestamp"].replace("Z", "+00:00"))
                hour = ts.strftime("%H:00")
                hourly[hour] = hourly.get(hour, 0) + 1
            except Exception:
                pass

    by_service: dict[str, int] = {}
    by_tier: dict[str, int] = {"hot": 0, "warm": 0, "cold": 0}
    for s in sessions:
        if s.service_category:
            key = s.service_category.value
            by_service[key] = by_service.get(key, 0) + 1
        if s.lead_tier:
            by_tier[s.lead_tier] = by_tier.get(s.lead_tier, 0) + 1

    return {
        "stats": {
            "active_sessions": len(active),
            "completed_enquiries": len(completed),
            "summaries_generated": len(completed),
            "whatsapp_conversations_today": whatsapp_today,
            "voice_calls_today": voice_today,
            "total_sessions": len(sessions),
            "leads_by_tier": by_tier,
            "leads_by_service": by_service,
        },
        "charts": {
            "messages_per_hour": hourly,
            "channel_distribution": {
                "whatsapp": whatsapp_today,
                "voice": voice_today,
            },
        },
        "generated_at": now.isoformat(),
    }


# ─── Sessions ─────────────────────────────────────────────────────────────────

@router.get("/sessions")
async def get_sessions(auth=Depends(require_admin)):
    sessions = await list_all_sessions()
    return {
        "sessions": [
            {
                "session_id": s.session_id,
                "phone_number": s.phone_number,
                "channel": s.channel,
                "active_consultant": s.active_consultant,
                "service_category": s.service_category.value if s.service_category else None,
                "conversation_stage": s.conversation_stage.value,
                "fields_collected": len(s.completed_fields),
                "field_completion_pct": s.field_completion_pct,
                "turn_count": s.turn_count,
                "summary_generated": s.summary_generated,
                "lead_score": s.lead_score,
                "lead_tier": s.lead_tier,
                "attachment_count": len(s.attachments),
                "last_active": s.last_active.isoformat(),
                "created_at": s.created_at.isoformat(),
            }
            for s in sorted(sessions, key=lambda x: x.last_active, reverse=True)
        ]
    }


@router.get("/session/{session_id}")
async def get_session_detail(session_id: str, auth=Depends(require_admin)):
    session = await get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    return {
        "session_id": session.session_id,
        "phone_number": session.phone_number,
        "channel": session.channel,
        "active_consultant": session.active_consultant,
        "service_category": session.service_category.value if session.service_category else None,
        "conversation_stage": session.conversation_stage.value,
        "lead_score": session.lead_score,
        "lead_tier": session.lead_tier,
        "attachments": [a.model_dump() for a in session.attachments],
        "flow_state": session.flow_state,
        "completed_fields": session.completed_fields,
        "extracted_fields": session.extracted_fields,
        "field_completion_pct": session.field_completion_pct,
        "turn_count": session.turn_count,
        "summary_generated": session.summary_generated,
        "summary": session.summary,
        "created_at": session.created_at.isoformat(),
        "last_active": session.last_active.isoformat(),
        "conversation_history": [
            {
                "role": msg.role.value,
                "content": msg.content,
                "timestamp": msg.timestamp.isoformat(),
                "extracted_fields": msg.extracted_fields,
            }
            for msg in session.conversation_history
        ],
        "thinking_traces": [
            {
                "turn": t.turn,
                "user_message": t.user_message,
                "detected_fields": t.detected_fields,
                "next_field_target": t.next_field_target,
                "stage_before": t.stage_before.value,
                "stage_after": t.stage_after.value,
                "guardrail_triggered": t.guardrail_triggered,
                "timestamp": t.timestamp.isoformat(),
            }
            for t in session.thinking_traces
        ],
    }


# ─── Presales (Tatva API) ─────────────────────────────────────────────────────

@router.get("/presales")
async def get_presales(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    flag: Optional[str] = Query(None),
    auth=Depends(require_admin),
):
    from backend.integrations.tatva_presales import fetch_presales_records
    from backend.crm import store as crm_store

    result = await fetch_presales_records(page=page, limit=limit, flag=flag)
    data = result.get("data") if isinstance(result.get("data"), dict) else {}
    items = data.get("items") if isinstance(data.get("items"), list) else []
    if crm_store.crm_available() and items:
        data["items"] = crm_store.enrich_presales_items(items)
        result["data"] = data
    result["crm_configured"] = crm_store.crm_available()
    return result


@router.get("/users")
async def get_tatva_users(
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=100),
    auth=Depends(require_admin),
):
    from backend.integrations.tatva_users import fetch_tatva_users

    return await fetch_tatva_users(page=page, limit=limit)


@router.get("/vendor-leads")
async def get_vendor_leads(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    status: Optional[str] = Query(None),
    auth=Depends(require_admin),
):
    from backend.integrations.tatva_vendor_leads import fetch_vendor_leads
    from backend.crm import store as crm_store

    result = await fetch_vendor_leads(page=page, limit=limit, status=status or None)
    data = result.get("data") if isinstance(result.get("data"), dict) else {}
    items = data.get("items") if isinstance(data.get("items"), list) else []
    if crm_store.crm_available() and items:
        data["items"] = crm_store.enrich_vendor_items(items)
        result["data"] = data
    result["crm_configured"] = crm_store.crm_available()
    return result


# ─── Enquiries ────────────────────────────────────────────────────────────────

def _live_session_to_enquiry(session) -> dict[str, Any]:
    from backend.storage.supabase_store import _all_enquiry_attachment_records

    status = "declined" if session.flow_state.get("project_declined") else "in_progress"
    if session.summary_generated:
        status = "completed"
    fields = dict(session.extracted_fields or {})
    fields["_enquiry_status"] = status
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
    return {
        "session_id": session.session_id,
        "phone_number": session.phone_number,
        "channel": session.channel,
        "service_category": session.service_category.value if session.service_category else None,
        "extracted_fields": fields,
        "completed_fields": session.completed_fields,
        "completion_pct": session.field_completion_pct,
        "lead_score": session.lead_score,
        "lead_tier": session.lead_tier,
        "status": status,
        "attachment_count": len(file_records),
        "attachments": file_records,
        "created_at": session.created_at.isoformat(),
        "last_active": session.last_active.isoformat(),
        "source": "live",
    }


@router.get("/enquiries")
async def get_enquiries(auth=Depends(require_staff)):
    from backend.crm import store as crm_store

    stored = await supabase_store.get_all_enquiries()
    by_session: dict[str, dict[str, Any]] = {
        str(row.get("session_id") or ""): row for row in stored if row.get("session_id")
    }

    for session in await list_all_sessions():
        if not session.extracted_fields:
            continue
        live = _live_session_to_enquiry(session)
        sid = live["session_id"]
        existing = by_session.get(sid)
        if existing:
            existing["completion_pct"] = max(
                int(existing.get("completion_pct") or 0),
                int(live.get("completion_pct") or 0),
            )
            if not existing.get("attachments") and live.get("attachments"):
                existing["attachments"] = live["attachments"]
                existing["attachment_count"] = live["attachment_count"]
            if live.get("status") == "in_progress":
                existing["status"] = "in_progress"
                existing["extracted_fields"] = live["extracted_fields"]
                existing["last_active"] = live["last_active"]
            continue
        by_session[sid] = live

    enquiries = sorted(
        by_session.values(),
        key=lambda row: str(row.get("last_active") or row.get("created_at") or ""),
        reverse=True,
    )

    role = auth.get("role")
    user_id = auth.get("user_id")
    scoped_to_assignments = False
    if role in {"presales", "rm"} and user_id:
        assigned_phones = crm_store.assigned_phones_for_staff(
            str(user_id),
            str(role),
        )
        enquiries = [
            row for row in enquiries
            if crm_store.enquiry_matches_assigned_phones(row, assigned_phones)
        ]
        scoped_to_assignments = True

    from backend.admin.enquiry_display import enrich_enquiries

    enquiries = await enrich_enquiries(enquiries)
    return {
        "enquiries": enquiries,
        "configured": supabase_store.is_configured(),
        "count": len(enquiries),
        "scoped_to_assignments": scoped_to_assignments,
    }


# ─── Summaries ────────────────────────────────────────────────────────────────

@router.get("/summaries")
async def get_summaries(auth=Depends(require_admin)):
    sessions = await list_all_sessions()
    return {
        "summaries": [
            s.summary for s in sessions if s.summary_generated and s.summary
        ]
    }


# ─── Logs ─────────────────────────────────────────────────────────────────────

@router.get("/logs")
async def get_logs(
    session_id: Optional[str] = Query(None),
    event: Optional[str] = Query(None),
    limit: int = Query(200, le=1000),
    auth=Depends(require_admin),
):
    logs = get_recent_logs(limit)
    if session_id:
        logs = [l for l in logs if l.get("session_id") == session_id]
    if event:
        logs = [l for l in logs if l.get("event") == event]
    return {"logs": logs, "count": len(logs)}


# ─── System Health ────────────────────────────────────────────────────────────

@router.get("/health")
async def get_health(auth=Depends(require_admin)):
    import httpx
    checks = {}

    # Gemini
    try:
        from google import genai as google_genai
        client = google_genai.Client(api_key=settings.gemini_api_key)
        client.models.generate_content(
            model=settings.gemini_model,
            contents="ping",
        )
        checks["gemini"] = {"status": "ok", "model": settings.gemini_model}
    except Exception as e:
        checks["gemini"] = {"status": "error", "error": str(e)[:100]}

    # Upstash Redis
    try:
        from backend.storage.redis_store import get_redis_store
        store = get_redis_store()
        if store.is_configured():
            async with httpx.AsyncClient(timeout=3.0) as c:
                r = await c.get(f"{settings.upstash_redis_rest_url}/ping",
                                headers={"Authorization": f"Bearer {settings.upstash_redis_rest_token}"})
                checks["redis"] = {"status": "ok" if r.status_code == 200 else "error"}
        else:
            checks["redis"] = {"status": "not_configured", "mode": "in_memory_fallback"}
    except Exception as e:
        checks["redis"] = {"status": "error", "error": str(e)[:80]}

    # Tatva PM API
    checks["tatva_api"] = {
        "status": "configured" if settings.tatva_users_api_base_url else "not_configured",
        "base_url": settings.tatva_users_api_base_url or "",
    }

    # Twilio
    checks["twilio"] = {
        "status": "configured" if settings.twilio_account_sid else "not_configured"
    }

    # Vapi
    checks["vapi"] = {
        "status": "configured" if settings.vapi_api_key else "not_configured"
    }

    # ElevenLabs
    checks["elevenlabs"] = {
        "status": "configured" if settings.elevenlabs_api_key else "not_configured"
    }

    overall = "healthy" if all(
        v.get("status") in ("ok", "configured", "not_configured")
        for v in checks.values()
    ) else "degraded"

    return {"overall": overall, "services": checks, "checked_at": datetime.utcnow().isoformat()}


# ─── Live SSE Stream ──────────────────────────────────────────────────────────

@router.get("/stream")
async def live_stream(request: Request, auth=Depends(require_admin_sse)):
    """Server-Sent Events stream for live admin monitor feed."""
    from backend.storage.redis_store import get_redis_store

    async def event_generator():
        store = get_redis_store()
        last_count = 0
        yield "data: {\"event\": \"connected\", \"message\": \"Live monitor active\"}\n\n"

        while True:
            if await request.is_disconnected():
                break
            try:
                logs = get_recent_logs(20)
                if len(logs) != last_count:
                    new_logs = logs[: len(logs) - last_count] if last_count > 0 else logs[:5]
                    for log in reversed(new_logs):
                        yield f"data: {json.dumps(log)}\n\n"
                    last_count = len(logs)
            except Exception:
                pass
            await asyncio.sleep(2)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


# ─── Attachments ──────────────────────────────────────────────────────────────

@router.get("/attachments")
async def list_attachments(
    session_id: Optional[str] = Query(None),
    auth=Depends(require_admin),
):
    sessions = await list_all_sessions()
    items = []
    for s in sessions:
        if session_id and s.session_id != session_id:
            continue
        for a in s.attachments:
            items.append({
                "session_id": s.session_id,
                "phone_number": s.phone_number,
                "service_category": s.service_category.value if s.service_category else None,
                **a.model_dump(),
            })
    return {"attachments": items}


@router.get("/session/{session_id}/attachments")
async def session_attachments(session_id: str, auth=Depends(require_admin)):
    return await list_attachments(session_id=session_id, auth=auth)


# ─── Manual Controls ──────────────────────────────────────────────────────────

@router.post("/session/{session_id}/reset")
async def reset_session(session_id: str, auth=Depends(require_admin)):
    """Delete session from store — client starts fresh on next message."""
    await delete_session(session_id)
    return {"status": "reset", "session_id": session_id}


@router.post("/session/{session_id}/force-summary")
async def force_summary(session_id: str, auth=Depends(require_admin)):
    """Force summary generation for a session, even if not all fields are collected."""
    session = await get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    from backend.summarizer.summary_generator import get_summary_generator
    from backend.storage.redis_store import save_session
    summarizer = get_summary_generator()
    summary = await summarizer.generate(session)
    from backend.intelligence.lead_scorer import apply_lead_score
    session.summary = summary.model_dump()
    session.summary_generated = True
    apply_lead_score(session)
    await save_session(session)
    return {"status": "summary_generated", "summary": session.summary, "lead_score": session.lead_score}


@router.post("/session/{session_id}/close")
async def close_session(session_id: str, auth=Depends(require_admin)):
    """Mark session as closed (summary_generated=True) without generating a summary."""
    session = await get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    from backend.schemas.session import ConversationStage
    from backend.storage.redis_store import save_session
    session.conversation_stage = ConversationStage.SUMMARY_GENERATED
    await save_session(session)
    return {"status": "closed", "session_id": session_id}

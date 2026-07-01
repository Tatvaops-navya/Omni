"""Public attachment preview URLs for WhatsApp final review."""
from __future__ import annotations

import hashlib
import hmac

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response

from backend.config import get_settings
from backend.integrations.tatva_enquiry_submit import _ATTACHMENT_KIND_LABELS, _attachment_kind
from backend.schemas.session import Session
from backend.storage.media_store import download_twilio_media
from backend.storage.redis_store import get_session

router = APIRouter(tags=["media"])


def _preview_secret() -> str:
    settings = get_settings()
    return (settings.admin_api_key or "changeme").strip()


def attachment_preview_token(session_id: str, index: int) -> str:
    msg = f"{session_id}:{index}".encode()
    return hmac.new(_preview_secret().encode(), msg, hashlib.sha256).hexdigest()[:32]


def verify_attachment_preview_token(session_id: str, index: int, token: str) -> bool:
    expected = attachment_preview_token(session_id, index)
    return hmac.compare_digest(expected, (token or "").strip())


def list_session_attachment_links(session: Session) -> list[dict[str, str]]:
    """Preview links for files uploaded in this session (before Tatva CDN URLs exist)."""
    links: list[dict[str, str]] = []
    for index, meta in enumerate(session.attachments or []):
        kind = _attachment_kind(
            url=str(meta.file_url or ""),
            key=str(meta.file_name or ""),
            mime=str(meta.mime_type or ""),
        )
        links.append({
            "label": f"↗ {_ATTACHMENT_KIND_LABELS[kind]}",
            "url": public_attachment_url(session.session_id, index),
            "kind": kind,
        })
    return links


def public_attachment_url(session_id: str, index: int) -> str:
    settings = get_settings()
    token = attachment_preview_token(session_id, index)
    base = settings.base_url.rstrip("/")
    return f"{base}/media/wa/{session_id}/{index}?t={token}"


def admin_attachment_preview_url(session_id: str, index: int) -> str:
    """Same-origin preview path for admin UI (Vite/Vercel proxy → backend)."""
    token = attachment_preview_token(session_id, index)
    return f"/media/wa/{session_id}/{index}?t={token}"


@router.get("/media/wa/{session_id}/{attachment_index}")
async def serve_whatsapp_attachment(
    session_id: str,
    attachment_index: int,
    t: str = Query(default=""),
):
    if attachment_index < 0 or not verify_attachment_preview_token(session_id, attachment_index, t):
        raise HTTPException(status_code=404, detail="Not found")

    meta = None
    session = await get_session(session_id)
    if session:
        attachments = list(session.attachments or [])
        if attachment_index < len(attachments):
            meta = attachments[attachment_index]

    if meta is None:
        from backend.storage.supabase_store import (
            _cache_attachment_row,
            _client as supabase_client,
            get_whatsapp_attachment_record,
        )

        record = get_whatsapp_attachment_record(session_id, attachment_index)
        if record and str(record.get("file_url") or "").startswith("twilio:"):
            record = await _cache_attachment_row(session_id, record)
            row_id = record.get("id")
            cached_url = str(record.get("file_url") or "")
            if row_id and cached_url and not cached_url.startswith("twilio:"):
                db = supabase_client()
                if db is not None:
                    try:
                        db.table("enquiry_attachments").update(
                            {"file_url": cached_url},
                        ).eq("id", row_id).execute()
                    except Exception:
                        pass
        if record:
            from backend.schemas.session import AttachmentMeta

            meta = AttachmentMeta(
                file_name=str(record.get("file_name") or "Uploaded file"),
                file_url=str(record.get("file_url") or ""),
                mime_type=str(record.get("mime_type") or ""),
            )

    if meta is None:
        raise HTTPException(status_code=404, detail="Not found")

    url = (meta.file_url or "").strip()
    if not url:
        raise HTTPException(status_code=404, detail="Not found")

    try:
        if url.startswith("twilio:"):
            twilio_url = url.split(":", 1)[-1]
            data, ctype = await download_twilio_media(twilio_url)
        else:
            import httpx

            async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
                response = await client.get(url)
                response.raise_for_status()
                data = response.content
                ctype = response.headers.get("content-type") or meta.mime_type or "application/octet-stream"
    except Exception:
        raise HTTPException(status_code=404, detail="Not found")

    return Response(
        content=data,
        media_type=ctype or meta.mime_type or "application/octet-stream",
        headers={"Cache-Control": "private, max-age=3600"},
    )

"""
WhatsApp media download — attachments kept on session metadata (Twilio URL reference).
"""
from __future__ import annotations
import uuid
from datetime import datetime
from typing import Optional

import httpx

from backend.config import get_settings
from backend.schemas.session import Session, AttachmentMeta

settings = get_settings()


async def download_twilio_media(media_url: str) -> tuple[bytes, str]:
    """Download media from Twilio with basic auth."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.get(
            media_url,
            auth=(settings.twilio_account_sid, settings.twilio_auth_token),
            follow_redirects=True,
        )
        r.raise_for_status()
        ctype = r.headers.get("content-type", "application/octet-stream")
        return r.content, ctype


async def save_attachment(
    session: Session,
    media_url: str,
    content_type: str = "",
    file_name: Optional[str] = None,
) -> Optional[AttachmentMeta]:
    """Download from Twilio and record metadata on the session."""
    if not media_url:
        return None
    try:
        data, ctype = await download_twilio_media(media_url)
        if not content_type:
            content_type = ctype
        ext = "jpg"
        if "png" in content_type:
            ext = "png"
        elif "pdf" in content_type:
            ext = "pdf"
        fname = file_name or f"{uuid.uuid4().hex[:12]}.{ext}"
        public_url = f"twilio:{media_url}"

        meta = AttachmentMeta(
            file_name=fname,
            file_url=public_url,
            mime_type=content_type,
            uploaded_at=datetime.utcnow(),
        )
        session.attachments.append(meta)
        return meta
    except Exception as e:
        print(f"[MediaStore] save_attachment error: {e}")
        return None

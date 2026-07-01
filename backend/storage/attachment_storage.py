"""Persist WhatsApp uploads to Supabase Storage for long-lived admin preview URLs."""
from __future__ import annotations

from typing import Optional

from backend.storage.supabase_client import get_supabase_client, is_supabase_configured

BUCKET = "enquiry-files"


def upload_enquiry_file(
    session_id: str,
    file_name: str,
    data: bytes,
    mime_type: str = "application/octet-stream",
) -> Optional[str]:
    if not is_supabase_configured() or not session_id or not data:
        return None
    client = get_supabase_client()
    if client is None:
        return None
    safe_name = (file_name or "upload").replace("\\", "/").split("/")[-1] or "upload"
    path = f"{session_id}/{safe_name}"
    try:
        storage = client.storage.from_(BUCKET)
        storage.upload(
            path,
            data,
            file_options={"content-type": mime_type or "application/octet-stream", "upsert": "true"},
        )
        return str(storage.get_public_url(path))
    except Exception as exc:
        print(f"[AttachmentStorage] upload failed for {path}: {exc}")
        return None

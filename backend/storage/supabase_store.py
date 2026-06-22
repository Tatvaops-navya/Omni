"""
Legacy storage module — Supabase removed. All operations are no-ops.
Session state lives in Redis/memory; profile and addresses come from Tatva PM API.
"""
from __future__ import annotations


def is_configured() -> bool:
    return False


def _get_client():
    return None


async def save_enquiry(session) -> bool:
    return False


async def persist_terminal_enquiry(session) -> bool:
    return False


async def save_summary(summary, phone_number: str = "") -> bool:
    return False


async def upsert_session_log(session) -> bool:
    return False


async def get_all_enquiries() -> list[dict]:
    return []


async def get_latest_enquiry_profile_by_phone(phone_number: str) -> dict[str, str]:
    return {}


async def get_all_summaries() -> list[dict]:
    return []


async def save_attachment_record(
    session_id: str,
    file_name: str,
    file_url: str,
    mime_type: str = "",
) -> bool:
    return False


async def get_all_attachments(session_id: str | None = None) -> list[dict]:
    return []

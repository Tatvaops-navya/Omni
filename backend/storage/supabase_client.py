"""Supabase client for Krsna CRM (lead assignments, CRM users)."""
from __future__ import annotations

from functools import lru_cache
from typing import Any

from backend.config import get_settings


@lru_cache
def is_supabase_configured() -> bool:
    settings = get_settings()
    return bool(
        (settings.supabase_url or "").strip()
        and (settings.supabase_service_role_key or "").strip()
    )


@lru_cache
def get_supabase_client() -> Any:
    if not is_supabase_configured():
        return None
    from supabase import create_client

    settings = get_settings()
    return create_client(
        settings.supabase_url.strip(),
        settings.supabase_service_role_key.strip(),
    )

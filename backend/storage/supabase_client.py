"""Supabase client for Krsna CRM (lead assignments, CRM users)."""
from __future__ import annotations

from functools import lru_cache
from typing import Any

from backend.config import get_settings


@lru_cache
def is_supabase_configured() -> bool:
    settings = get_settings()
    url = (getattr(settings, "supabase_url", None) or "").strip()
    key = (getattr(settings, "supabase_service_role_key", None) or "").strip()
    return bool(url and key)


@lru_cache
def get_supabase_client() -> Any:
    if not is_supabase_configured():
        return None
    try:
        from supabase import create_client
    except ImportError:
        return None

    settings = get_settings()
    try:
        return create_client(
            settings.supabase_url.strip(),
            settings.supabase_service_role_key.strip(),
        )
    except Exception:
        return None

"""
Aadhya ΓÇô Admin Panel Authentication
Admin password, CRM team login, and API key protection for /krsna routes.
"""
from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import APIKeyHeader

from backend.config import get_settings

settings = get_settings()

TOKEN_EXPIRY_HOURS = 8
API_KEY_HEADER = APIKeyHeader(name="X-Admin-Key", auto_error=False)


@dataclass
class AuthSession:
    expiry: datetime
    role: str = "admin"
    user_id: str | None = None
    name: str | None = None
    email: str | None = None


_active_tokens: dict[str, AuthSession] = {}


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def generate_session_token(
    *,
    role: str = "admin",
    user_id: str | None = None,
    name: str | None = None,
    email: str | None = None,
) -> str:
    token = secrets.token_urlsafe(32)
    _active_tokens[token] = AuthSession(
        expiry=datetime.utcnow() + timedelta(hours=TOKEN_EXPIRY_HOURS),
        role=role,
        user_id=user_id,
        name=name,
        email=email,
    )
    return token


def invalidate_token(token: str) -> None:
    _active_tokens.pop(token, None)


def get_auth_session(token: str) -> AuthSession | None:
    session = _active_tokens.get(token)
    if not session:
        return None
    if datetime.utcnow() > session.expiry:
        _active_tokens.pop(token, None)
        return None
    return session


def is_valid_token(token: str) -> bool:
    return get_auth_session(token) is not None


def _token_from_request(request: Request, query_token: str | None = None) -> str | None:
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth[7:].strip() or None
    if query_token:
        return query_token.strip() or None
    return None


def _resolve_auth_context(
    request: Request,
    api_key: Optional[str],
    query_token: Optional[str] = None,
) -> dict:
    if api_key and api_key == settings.admin_api_key:
        return {"method": "api_key", "role": "admin", "user_id": None}

    token = _token_from_request(request, query_token)
    if token:
        session = get_auth_session(token)
        if session:
            return {
                "method": "session_token",
                "role": session.role,
                "user_id": session.user_id,
                "name": session.name,
                "email": session.email,
            }

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required",
    )


async def require_staff(
    request: Request,
    api_key: Optional[str] = Depends(API_KEY_HEADER),
):
    """Admin and supported CRM team members."""
    ctx = _resolve_auth_context(request, api_key)
    if ctx.get("method") == "api_key" or ctx.get("role") in {
        "admin",
        "presales",
        "rm",
        "campaign_owner",
    }:
        return ctx
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Staff access required")


async def require_admin(
    request: Request,
    api_key: Optional[str] = Depends(API_KEY_HEADER),
):
    ctx = _resolve_auth_context(request, api_key)
    if ctx.get("method") == "api_key" or ctx.get("role") == "admin":
        return ctx
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")


async def require_auth(
    request: Request,
    api_key: Optional[str] = Depends(API_KEY_HEADER),
):
    return _resolve_auth_context(request, api_key)


async def require_admin_sse(
    request: Request,
    api_key: Optional[str] = Depends(API_KEY_HEADER),
    token: Optional[str] = None,
):
    return _resolve_auth_context(request, api_key, query_token=token)


# Back-compat alias used by older imports
verify_admin_api_key = require_admin

"""
Aadhya – Upstash Redis Session Store
Uses Upstash REST API (no redis-py dependency needed) via httpx.
"""
from __future__ import annotations
import json
from typing import Optional
import httpx

from backend.config import get_settings
from backend.schemas.session import Session

settings = get_settings()


class RedisStore:
    def __init__(self):
        self.base_url = settings.upstash_redis_rest_url.rstrip("/")
        self.token = settings.upstash_redis_rest_token
        self.ttl = settings.session_ttl_hours * 3600
        self._headers = {"Authorization": f"Bearer {self.token}"}

    def is_configured(self) -> bool:
        return bool(self.base_url and self.token
                    and self.base_url != "https://your-db.upstash.io")

    async def _request(self, *command_parts) -> dict:
        url = self.base_url + "/" + "/".join(str(p) for p in command_parts)
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(url, headers=self._headers)
            response.raise_for_status()
            return response.json()

    async def _post(self, payload) -> dict:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.post(
                self.base_url,
                headers={**self._headers, "Content-Type": "application/json"},
                content=json.dumps(payload),
            )
            response.raise_for_status()
            return response.json()

    async def get_session(self, session_id: str) -> Optional[Session]:
        if not self.is_configured():
            return None
        try:
            result = await self._request("GET", f"session:{session_id}")
            raw = result.get("result")
            if raw:
                return Session.model_validate_json(raw)
        except Exception:
            pass
        return None

    async def save_session(self, session: Session) -> bool:
        if not self.is_configured():
            return False
        try:
            key = f"session:{session.session_id}"
            data = session.model_dump_json()
            # Must use POST; GET URL queries break on large JSON and spaces.
            await self._post(["SET", key, data, "EX", str(self.ttl)])
            return True
        except Exception:
            return False

    async def delete_session(self, session_id: str) -> bool:
        if not self.is_configured():
            return False
        try:
            await self._request("DEL", f"session:{session_id}")
            return True
        except Exception:
            return False

    async def list_session_ids(self) -> list[str]:
        """Returns all active session IDs using SCAN (safe for production Redis)."""
        if not self.is_configured():
            return []
        try:
            session_ids: list[str] = []
            cursor = 0
            while True:
                # SCAN cursor MATCH pattern COUNT hint
                result = await self._request("SCAN", cursor, "MATCH", "session:*", "COUNT", 100)
                data = result.get("result", [])
                # Upstash REST returns [next_cursor, [keys...]]
                if isinstance(data, list) and len(data) == 2:
                    cursor = int(data[0])
                    keys = data[1] if isinstance(data[1], list) else []
                else:
                    # Unexpected shape — fall back to empty
                    break
                session_ids.extend(k.replace("session:", "") for k in keys)
                if cursor == 0:
                    break  # Full scan complete
            return session_ids
        except Exception:
            return []

    async def lpush_capped(self, key: str, value: str, max_len: int):
        """Push to list and trim to max_len (for log feed)."""
        if not self.is_configured():
            return
        try:
            payload = [["LPUSH", key, value], ["LTRIM", key, 0, max_len - 1]]
            await self._post(payload)
        except Exception:
            pass

    async def claim_idempotency_key(self, key: str, *, ttl_sec: int = 600) -> bool:
        """Return True when this key was newly claimed (SET NX). False if already seen."""
        if not self.is_configured():
            return True
        try:
            result = await self._post(["SET", key, "1", "NX", "EX", str(ttl_sec)])
            return result.get("result") == "OK"
        except Exception:
            return True

    async def get_logs(self, n: int = 100) -> list[dict]:
        """Get recent log entries from Redis."""
        if not self.is_configured():
            return []
        try:
            result = await self._request("LRANGE", REDIS_LOG_KEY, 0, n - 1)
            entries = result.get("result", [])
            return [json.loads(e) for e in entries]
        except Exception:
            return []


REDIS_LOG_KEY = "aadhya:logs"

# In-memory fallback when Redis is not configured
_memory_sessions: dict[str, Session] = {}


class InMemoryStore:
    """Fallback store for local dev without Upstash."""

    async def get_session(self, session_id: str) -> Optional[Session]:
        return _memory_sessions.get(session_id)

    async def save_session(self, session: Session) -> bool:
        _memory_sessions[session.session_id] = session
        return True

    async def delete_session(self, session_id: str) -> bool:
        _memory_sessions.pop(session_id, None)
        return True

    async def list_session_ids(self) -> list[str]:
        return list(_memory_sessions.keys())

    async def get_session_by_id(self, session_id: str) -> Optional[Session]:
        return _memory_sessions.get(session_id)

    async def all_sessions(self) -> list[Session]:
        return list(_memory_sessions.values())

    def is_configured(self) -> bool:
        return True  # Always available


_redis: RedisStore | None = None
_memory: InMemoryStore | None = None


def get_redis_store() -> RedisStore:
    global _redis
    if _redis is None:
        _redis = RedisStore()
    return _redis


def get_memory_store() -> InMemoryStore:
    global _memory
    if _memory is None:
        _memory = InMemoryStore()
    return _memory


async def get_session(session_id: str) -> Optional[Session]:
    """Get session — tries Redis first, falls back to memory."""
    redis = get_redis_store()
    if redis.is_configured():
        session = await redis.get_session(session_id)
        if session:
            return session
    return await get_memory_store().get_session(session_id)


async def save_session(session: Session) -> None:
    """Save session to Redis and memory."""
    redis = get_redis_store()
    if redis.is_configured():
        await redis.save_session(session)
    await get_memory_store().save_session(session)


async def delete_session(session_id: str) -> None:
    redis = get_redis_store()
    if redis.is_configured():
        await redis.delete_session(session_id)
    await get_memory_store().delete_session(session_id)


async def list_all_sessions() -> list[Session]:
    """Returns all sessions from Redis SCAN merged with in-memory store."""
    seen: dict[str, Session] = {}
    memory = get_memory_store()
    for s in await memory.all_sessions():
        seen[s.session_id] = s

    redis = get_redis_store()
    if redis.is_configured():
        for sid in await redis.list_session_ids():
            if sid in seen:
                continue
            session = await redis.get_session(sid)
            if session:
                seen[sid] = session

    return sorted(seen.values(), key=lambda x: x.last_active, reverse=True)


_idempotency_memory: dict[str, float] = {}


async def _claim_idempotency_key_local(key: str, *, ttl_sec: int) -> bool:
    import time

    now = time.time()
    expired = [k for k, exp in _idempotency_memory.items() if exp <= now]
    for k in expired:
        _idempotency_memory.pop(k, None)
    if key in _idempotency_memory:
        return False
    _idempotency_memory[key] = now + ttl_sec
    return True


async def claim_idempotency_key(key: str, *, ttl_sec: int = 600) -> bool:
    """Return True when this dedupe key is new."""
    needle = str(key or "").strip()
    if not needle:
        return True

    redis = get_redis_store()
    if redis.is_configured():
        return await redis.claim_idempotency_key(f"wa:dedup:{needle}", ttl_sec=ttl_sec)
    return await _claim_idempotency_key_local(needle, ttl_sec=ttl_sec)


async def claim_inbound_message(
    message_sid: str = "",
    *,
    phone_number: str = "",
    user_message: str = "",
    ttl_sec: int = 600,
) -> bool:
    """
    Deduplicate Twilio webhook retries / multi-instance double delivery.
    Uses MessageSid when present, plus a short phone+body bucket for retries
    that arrive with a different Sid.
    """
    import hashlib
    import time

    keys: list[str] = []
    sid = str(message_sid or "").strip()
    if sid:
        keys.append(f"sid:{sid}")

    norm = (user_message or "").strip().lower().replace(" ", "")
    phone = str(phone_number or "").strip()
    if phone and norm:
        bucket = int(time.time()) // 15
        digest = hashlib.sha256(f"{phone}|{norm}|{bucket}".encode()).hexdigest()[:24]
        keys.append(f"body:{digest}")

    if not keys:
        return True

    for key in keys:
        if not await claim_idempotency_key(key, ttl_sec=ttl_sec):
            return False
    return True

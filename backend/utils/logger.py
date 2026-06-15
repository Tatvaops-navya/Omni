"""
Aadhya – Structured Logger
Emits JSON events to stdout, file, and Upstash Redis (for live admin feed).
"""
from __future__ import annotations
import json
import asyncio
from datetime import datetime
from pathlib import Path
from typing import Any

LOG_FILE = Path("logs/aadhya.jsonl")
LOG_FILE.parent.mkdir(exist_ok=True)

# Redis log list key and max items
REDIS_LOG_KEY = "aadhya:logs"
REDIS_LOG_MAX = 1000


def _build_entry(event: str, session_id: str, data: dict) -> dict:
    return {
        "event": event,
        "session_id": session_id,
        "timestamp": datetime.utcnow().isoformat() + "Z",
        **data,
    }


def _write_to_file(entry: dict):
    try:
        with LOG_FILE.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception:
        pass


def _print_log(entry: dict):
    # Colorized console output
    event = entry.get("event", "")
    colors = {
        "SESSION_START": "\033[96m",      # Cyan
        "USER_MESSAGE": "\033[92m",       # Green
        "GEMINI_RESPONSE": "\033[94m",    # Blue
        "EXTRACTED_FIELDS": "\033[93m",   # Yellow
        "NEXT_FIELD_DECISION": "\033[95m",# Magenta
        "STAGE_TRANSITION": "\033[96m",   # Cyan
        "SUMMARY_GENERATED": "\033[92m",  # Green bold
        "GUARDRAIL_TRIGGERED": "\033[91m",# Red
        "API_ERROR": "\033[91m",          # Red
        "TATVA_SERVICE_QUESTIONS_FETCH": "\033[96m",  # Cyan
        "TATVA_SERVICE_QUESTIONS_OK": "\033[92m",     # Green
        "SERVICE_QUESTIONS_LOADED": "\033[93m",       # Yellow
    }
    color = colors.get(event, "\033[0m")
    reset = "\033[0m"
    print(f"{color}[{entry['timestamp']}] {event} | session={entry['session_id']}{reset}")
    # Print relevant data fields (not timestamp/event/session_id)
    extra = {k: v for k, v in entry.items()
             if k not in ("event", "session_id", "timestamp")}
    if extra:
        print(f"  {json.dumps(extra, default=str)}")


async def _push_to_redis(entry: dict):
    """Push log entry to Upstash Redis list for live admin feed."""
    try:
        from backend.config import get_settings
        from backend.storage.redis_store import get_redis_store
        store = get_redis_store()
        if store.is_configured():
            await store.lpush_capped(REDIS_LOG_KEY, json.dumps(entry), REDIS_LOG_MAX)
    except Exception:
        pass  # Non-critical


async def log_event(event: str, session_id: str = "system", data: dict | None = None):
    """Main logging function. Call with await."""
    entry = _build_entry(event, session_id, data or {})
    _print_log(entry)
    _write_to_file(entry)
    # Best-effort Redis push (non-critical)
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_push_to_redis(entry))
    except RuntimeError:
        pass  # No running event loop — skip Redis push


def get_recent_logs(n: int = 200) -> list[dict]:
    """Read last n log entries from file for admin panel."""
    if not LOG_FILE.exists():
        return []
    lines = LOG_FILE.read_text(encoding="utf-8").strip().split("\n")
    recent = lines[-n:]
    result = []
    for line in reversed(recent):
        try:
            result.append(json.loads(line))
        except Exception:
            continue
    return result

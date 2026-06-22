"""
Session idle timeout — end in-progress chats after inactivity.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta

from backend.config import get_settings
from backend.schemas.session import Session, ConversationStage


def idle_timeout_minutes() -> int:
    return get_settings().session_idle_timeout_minutes


def is_session_idle_expired(session: Session) -> bool:
    """In-progress sessions expire after SESSION_IDLE_TIMEOUT_MINUTES without a message."""
    if session.summary_generated or session.conversation_stage == ConversationStage.SUMMARY_GENERATED:
        return False
    minutes = idle_timeout_minutes()
    if minutes <= 0:
        return False
    return datetime.utcnow() - session.last_active > timedelta(minutes=minutes)


def idle_timeout_notice() -> str:
    mins = idle_timeout_minutes()
    return (
        f"This chat ended after {mins} minutes of inactivity. "
        "Let's start fresh.\n\n"
    )


def _normalize_msg(message: str) -> str:
    return (message or "").strip().upper().replace(" ", "")


_GREETING_EXACT = frozenset({
    "HI", "HII", "HIII", "HIIII", "HIIIII",
    "HELLO", "HELLOO", "HELLOOO",
    "HEY", "HEYY", "HEYYY", "HEYA",
    "HLO", "HLW", "HOWDY", "YO",
    "HITHERE", "HELLOTHERE", "HEYTHERE",
    "NAMASTE", "NAMASKAR", "NAMASKARAM",
    "NEWENQUIRY", "NEWPROJECT", "STARTOVER", "STARTAGAIN",
})

_CASUAL_GREETING_SUFFIXES = frozenset({
    "BRO", "ANNA", "BABY", "DUDE", "BHAI", "SIS", "MATE", "YAAR", "DEAR",
})

_CASUAL_GREETING_WORDS = frozenset({
    "bro", "anna", "baby", "dude", "bhai", "sis", "mate", "yaar", "dear", "there",
})


def _greeting_stem(norm: str) -> bool:
    if not norm:
        return False
    if norm in _GREETING_EXACT:
        return True
    if re.fullmatch(r"H+I+", norm):
        return True
    if re.fullmatch(r"HELLO+", norm):
        return True
    if re.fullmatch(r"HEY+", norm):
        return True
    if norm.startswith("NAMASTE") or norm.startswith("NAMASKAR"):
        return True
    return False


def is_greeting_message(message: str) -> bool:
    """Hi/Hello/Namaste-style openers — not names like Hitesh or Vidya."""
    return is_pure_greeting_message(message)


def is_pure_greeting_message(message: str) -> bool:
    """
    Short typed greetings only — not quoted WhatsApp replies that embed EVA welcome text.
    """
    raw = (message or "").strip()
    if not raw:
        return False
    lines = [ln.strip() for ln in raw.replace("\r", "\n").split("\n") if ln.strip()]
    if len(lines) > 2:
        return False
    if len(raw) > 80:
        return False
    norm = _normalize_msg(raw)
    if _greeting_stem(norm):
        return True
    if norm.startswith("GOOD") and any(
        part in norm for part in ("MORNING", "EVENING", "AFTERNOON", "NIGHT")
    ):
        return True
    for suffix in _CASUAL_GREETING_SUFFIXES:
        if norm.endswith(suffix):
            base = norm[: -len(suffix)]
            if _greeting_stem(base):
                return True
    words = re.sub(r"[^\w\s]", "", raw.lower()).split()
    if not words:
        return False
    first = words[0]
    rest = words[1:]
    if re.fullmatch(r"h+i+", first) or first in ("hello", "hey", "hi", "hlo", "hlw"):
        if not rest or all(w in _CASUAL_GREETING_WORDS for w in rest):
            return True
    if first in ("namaste", "namaskar", "namaskaram"):
        if not rest or all(w in _CASUAL_GREETING_WORDS for w in rest):
            return True
    if first == "good" and any(w in rest for w in ("morning", "evening", "afternoon", "night")):
        return True
    return False


def had_conversation_progress(session: Session) -> bool:
    """True once the user has moved past the opening welcome."""
    stage = session.flow_state.get("current_stage", "ava_intro")
    if stage != "ava_intro":
        return True
    if session.turn_count > 0:
        return True
    if session.completed_fields:
        return True
    if any(m.role.value == "user" for m in session.conversation_history):
        return True
    return False


def should_prepend_idle_notice(session: Session, user_message: str) -> bool:
    """Only show the timeout banner when resuming mid-flow, not a fresh EVA start."""
    if is_greeting_message(user_message):
        return False
    return had_conversation_progress(session)


def build_idle_fresh_start_reply(stale_session: Session, user_message: str) -> str:
    """
    Full EVA welcome after idle timeout.
    The inbound message is discarded — user must answer from the name question onward.
    """
    from backend.intelligence import hybrid_flow

    notice = (
        idle_timeout_notice()
        if should_prepend_idle_notice(stale_session, user_message)
        else ""
    )
    return notice + hybrid_flow.first_client_message()


async def clear_cached_session(session_id: str, *, reason: str) -> None:
    """Remove session from Redis and in-memory store after enquiry completion."""
    from backend.storage.redis_store import delete_session
    from backend.utils.logger import log_event

    await delete_session(session_id)
    await log_event(
        "SESSION_CLEARED",
        session_id=session_id,
        data={"reason": reason},
    )


async def start_fresh_session(
    session_id: str,
    phone_number: str,
    *,
    channel: str = "whatsapp",
    reason: str,
) -> Session:
    """Delete stored state and persist a new empty session."""
    from backend.storage.redis_store import save_session
    from backend.utils.logger import log_event

    await clear_cached_session(session_id, reason=reason)
    await log_event(
        "SESSION_RESET",
        session_id=session_id,
        data={"reason": reason, "channel": channel},
    )
    new_session = Session(
        session_id=session_id,
        phone_number=phone_number,
        channel=channel,
        conversation_stage=ConversationStage.ROUTING,
        flow_state={"current_stage": "ava_intro", "completed_stages": [], "pending_fields": []},
        created_at=datetime.utcnow(),
        last_active=datetime.utcnow(),
    )
    await save_session(new_session)
    return new_session

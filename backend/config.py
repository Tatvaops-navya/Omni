"""
Aadhya – AI Interior Design Consultant
Configuration via environment variables (Pydantic Settings)
"""
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache
from typing import List

# Project root (parent of backend/) — load .env from here regardless of shell cwd
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_ENV_FILE = _PROJECT_ROOT / ".env"


from urllib.parse import urlparse


def _normalize_cors_origin(origin: str) -> str:
    """Browser Origin is scheme+host only — strip accidental paths like /krsna."""
    raw = origin.strip()
    if not raw or raw == "*":
        return raw
    parsed = urlparse(raw)
    if parsed.scheme and parsed.netloc:
        return f"{parsed.scheme}://{parsed.netloc}"
    return raw.rstrip("/")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE) if _ENV_FILE.exists() else ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Gemini
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.0-flash"

    # Twilio
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_whatsapp_from: str = "whatsapp:+14155238886"
    # Set true only after Twilio Content templates for quick-reply buttons are configured
    twilio_whatsapp_quick_reply: bool = False
    # Twilio Content template SID for interactive WhatsApp MCQ/list messages
    # The template should support content variables for prompt/options/payloads.
    twilio_whatsapp_interactive_content_sid: str = ""
    # Variable MCQ list pickers — see scripts/create_mcq_list_content.py
    twilio_mcq_list_1_content_sid: str = ""
    twilio_mcq_list_2_content_sid: str = ""
    twilio_mcq_list_4_content_sid: str = ""
    twilio_mcq_list_5_content_sid: str = ""
    # Variable-based list picker for service menu (no AVA welcome). See scripts/create_service_list_content.py
    twilio_service_selection_content_sid: str = ""

    # Vapi
    vapi_api_key: str = ""
    vapi_assistant_id: str = ""

    # ElevenLabs
    elevenlabs_api_key: str = ""
    elevenlabs_voice_id: str = ""

    # Upstash Redis
    upstash_redis_rest_url: str = ""
    upstash_redis_rest_token: str = ""
    session_ttl_hours: int = 24
    # End in-progress WhatsApp/voice chats after this many minutes without a user reply
    session_idle_timeout_minutes: int = 5

    # Supabase
    supabase_url: str = ""
    supabase_service_key: str = ""

    # Admin
    admin_password: str = "changeme"
    admin_api_key: str = "changeme"

    # App
    environment: str = "development"
    log_level: str = "INFO"
    host: str = "0.0.0.0"
    port: int = 8000
    # Hot-reload for `python -m backend` — defaults on when ENVIRONMENT=development
    reload_override: bool | None = Field(default=None, validation_alias="RELOAD")
    # Public-facing base URL — used by Vapi to self-reference the webhook URL
    # Set this to your deployed domain, e.g. https://aadhya.onrender.com
    base_url: str = "http://localhost:8000"
    # Allowed CORS origins — comma-separated, e.g. https://omni-rho-snowy.vercel.app
    # Must be origin only (scheme + host + port). Do NOT append paths like /krsna.
    cors_origins: str = "*"

    @property
    def uvicorn_reload(self) -> bool:
        """Hot-reload when running via python -m backend (default: on in development)."""
        if self.reload_override is not None:
            return self.reload_override
        return self.environment == "development"

    @property
    def cors_origins_list(self) -> List[str]:
        """Parse the comma-separated CORS_ORIGINS env var into a list."""
        if self.cors_origins.strip() == "*":
            return ["*"]
        seen: set[str] = set()
        out: List[str] = []
        for origin in self.cors_origins.split(","):
            normalized = _normalize_cors_origin(origin)
            if normalized and normalized not in seen:
                seen.add(normalized)
                out.append(normalized)
        return out


@lru_cache
def get_settings() -> Settings:
    return Settings()

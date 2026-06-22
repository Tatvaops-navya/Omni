#!/usr/bin/env python3
"""
Create Twilio WhatsApp quick-reply template for the initial Say Hi button.

  python scripts/create_say_hi_quick_reply_content.py

Add the printed SID to .env / Render:
  TWILIO_SAY_HI_QUICK_REPLY_CONTENT_SID=HX...
"""
from __future__ import annotations

import sys
from pathlib import Path

import requests
from requests.auth import HTTPBasicAuth

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.config import get_settings  # noqa: E402


def main() -> None:
    cfg = get_settings()
    if not cfg.twilio_account_sid or not cfg.twilio_auth_token:
        print("Set TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN in .env")
        sys.exit(1)

    payload = {
        "friendly_name": "tatvaops_say_hi_quick_reply",
        "language": "en",
        "variables": {
            "1": "Welcome to TatvaOps! You can tap on one of these options:",
        },
        "types": {
            "twilio/quick-reply": {
                "body": "{{1}}",
                "actions": [
                    {
                        "title": "Hi",
                        "id": "hi",
                    }
                ],
            }
        },
    }

    resp = requests.post(
        "https://content.twilio.com/v1/Content",
        auth=HTTPBasicAuth(cfg.twilio_account_sid, cfg.twilio_auth_token),
        json=payload,
        timeout=60,
    )
    if resp.status_code >= 400:
        print(f"Error {resp.status_code}: {resp.text}")
        sys.exit(1)

    sid = resp.json().get("sid", "")
    print("Created Say Hi quick-reply template (tappable Hi button).")
    print(f"TWILIO_SAY_HI_QUICK_REPLY_CONTENT_SID={sid}")
    print("\nAdd to .env and Render, then restart the backend.")


if __name__ == "__main__":
    main()

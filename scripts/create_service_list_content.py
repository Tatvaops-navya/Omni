#!/usr/bin/env python3
"""
Create a Twilio WhatsApp list-picker for the TatvaOps service menu.

  python scripts/create_service_list_content.py          # 6 rows (default, matches current template)
  python scripts/create_service_list_content.py --rows 10  # max WhatsApp rows

Update TWILIO_SERVICE_SELECTION_CONTENT_SID in .env and set WHATSAPP_SERVICE_LIST_ROWS in
backend/schemas/service.py to match.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import requests
from requests.auth import HTTPBasicAuth

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.config import get_settings  # noqa: E402
from backend.schemas.service import SERVICE_MENU, SERVICE_WHATSAPP_LABELS  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rows", type=int, default=6, choices=(6, 10), help="List-picker row count")
    args = parser.parse_args()
    row_count = args.rows

    cfg = get_settings()
    if not cfg.twilio_account_sid or not cfg.twilio_auth_token:
        print("Set TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN in .env")
        sys.exit(1)

    variables: dict[str, str] = {"prompt": "Which TatvaOps service do you need?"}
    items = []
    for i in range(1, row_count + 1):
        variables[f"option_{i}_label"] = f"{{{{option_{i}_label}}}}"
        variables[f"option_{i}_value"] = f"{{{{option_{i}_value}}}}"
        variables[f"option_{i}_description"] = f"{{{{option_{i}_description}}}}"
        items.append({
            "id": f"{{{{option_{i}_value}}}}",
            "item": f"{{{{option_{i}_label}}}}",
            "description": f"{{{{option_{i}_description}}}}",
        })

    payload = {
        "friendly_name": f"tatvaops_service_menu_{row_count}",
        "language": "en",
        "variables": variables,
        "types": {
            "twilio/list-picker": {
                "body": "{{prompt}}",
                "button": "Choose service",
                "items": items,
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
    print(f"Created {row_count}-row Content template.")
    print(f"TWILIO_SERVICE_SELECTION_CONTENT_SID={sid}")
    print(f"\nSet WHATSAPP_SERVICE_LIST_ROWS = {row_count} in backend/schemas/service.py")
    if row_count == 6:
        print("Page 1: services 1–5 + View more. Page 2: services 6–11.")
    else:
        print("Page 1: services 1–9 + More (10–11). Page 2: services 10–11.")
    print("\nAdd SID to .env and restart uvicorn.")


if __name__ == "__main__":
    main()

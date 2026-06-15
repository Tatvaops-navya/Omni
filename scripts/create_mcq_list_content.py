#!/usr/bin/env python3
"""
Create a Twilio WhatsApp list-picker for service MCQ questions (variable prompt + options).

  python scripts/create_mcq_list_content.py --rows 5
  python scripts/create_mcq_list_content.py --rows 4
  python scripts/create_mcq_list_content.py --rows 3
  python scripts/create_mcq_list_content.py --rows 2
  python scripts/create_mcq_list_content.py --rows 1

Set the printed SID in .env:
  TWILIO_MCQ_LIST_5_CONTENT_SID=HX...
  TWILIO_MCQ_LIST_4_CONTENT_SID=HX...
  TWILIO_MCQ_LIST_3_CONTENT_SID=HX...
  TWILIO_MCQ_LIST_2_CONTENT_SID=HX...
  TWILIO_MCQ_LIST_1_CONTENT_SID=HX...
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


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rows", type=int, required=True, choices=(1, 2, 3, 4, 5, 6), help="List-picker row count")
    args = parser.parse_args()
    row_count = args.rows

    cfg = get_settings()
    if not cfg.twilio_account_sid or not cfg.twilio_auth_token:
        print("Set TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN in .env")
        sys.exit(1)

    variables: dict[str, str] = {"prompt": "{{prompt}}"}
    items = []
    for i in range(1, row_count + 1):
        variables[f"option_{i}_label"] = f"{{{{option_{i}_label}}}}"
        variables[f"option_{i}_value"] = f"{{{{option_{i}_value}}}}"
        items.append({
            "id": f"{{{{option_{i}_value}}}}",
            "item": f"{{{{option_{i}_label}}}}",
            "description": "",
        })

    payload = {
        "friendly_name": f"tatvaops_mcq_list_{row_count}",
        "language": "en",
        "variables": variables,
        "types": {
            "twilio/list-picker": {
                "body": "{{prompt}}",
                "button": "Choose option",
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
    env_key = f"TWILIO_MCQ_LIST_{row_count}_CONTENT_SID"
    print(f"Created {row_count}-row variable MCQ list template.")
    print(f"{env_key}={sid}")
    print("\nAdd to .env and Render, then restart the backend.")


if __name__ == "__main__":
    main()

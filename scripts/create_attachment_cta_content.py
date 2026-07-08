#!/usr/bin/env python3
"""
Create Twilio WhatsApp call-to-action templates for enquiry attachment links.

Each template shows a short label in the body and a tappable button (no raw URL text).

Each template shows a short label in the body and a tappable green button (no inline image preview).

  python scripts/create_attachment_cta_content.py

Add the printed SIDs to .env / Render:
  TWILIO_CTA_VIEW_IMAGE_CONTENT_SID=HX...
  TWILIO_CTA_VIEW_PDF_CONTENT_SID=HX...
  TWILIO_CTA_VIEW_VIDEO_CONTENT_SID=HX...
  TWILIO_CTA_VIEW_FILE_CONTENT_SID=HX...

Optional (Tatva CDN attachments only):
  TATVA_ATTACHMENT_CDN_BASE_URL=https://d187u6mpwmtl08.cloudfront.net/
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

_KINDS: tuple[tuple[str, str, str], ...] = (
    ("image", "View image", "TWILIO_CTA_VIEW_IMAGE_CONTENT_SID"),
    ("pdf", "View PDF", "TWILIO_CTA_VIEW_PDF_CONTENT_SID"),
    ("video", "View video", "TWILIO_CTA_VIEW_VIDEO_CONTENT_SID"),
    ("file", "View file", "TWILIO_CTA_VIEW_FILE_CONTENT_SID"),
)


def _create_template(*, cfg, kind: str, button_title: str) -> str:
    sample_url = "https://d187u6mpwmtl08.cloudfront.net/enquiries/sample/path/file.png"
    payload = {
        "friendly_name": f"tatvaops_attachment_{kind}_cta",
        "language": "en",
        "variables": {
            "1": "View image",
            "2": sample_url,
        },
        "types": {
            "twilio/call-to-action": {
                "body": "{{1}}",
                "actions": [
                    {
                        "type": "URL",
                        "title": button_title[:20],
                        "url": "{{2}}",
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
        print(f"Error creating {kind} template {resp.status_code}: {resp.text}")
        sys.exit(1)
    return str(resp.json().get("sid") or "")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--cdn-base",
        default="https://d187u6mpwmtl08.cloudfront.net/",
        help="Public CDN origin used in template URL (must match enquiry attachment host)",
    )
    args = parser.parse_args()

    cfg = get_settings()
    if not cfg.twilio_account_sid or not cfg.twilio_auth_token:
        print("Set TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN in .env")
        sys.exit(1)

    print(f"Using CDN base: {args.cdn_base.rstrip('/')}/")
    print()
    for kind, title, env_key in _KINDS:
        sid = _create_template(cfg=cfg, kind=kind, button_title=title)
        print(f"{env_key}={sid}")
    print()
    print(f"TATVA_ATTACHMENT_CDN_BASE_URL={args.cdn_base.rstrip('/')}/")
    print("\nAdd these to .env and Render, then restart the backend.")


if __name__ == "__main__":
    main()

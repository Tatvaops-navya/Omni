"""
Submit completed service questionnaire to withtatva.ai enquiries API.
"""
from __future__ import annotations

import json
from typing import Any, Optional

import httpx

from backend.config import get_settings
from backend.intelligence.display_labels import display_label, prompt_to_client_label
from backend.intelligence.qualification_builder import get_service_questionnaire_steps
from backend.integrations.tatva_users import register_tatva_user_for_session
from backend.schemas.service import get_service_mongo_id
from backend.schemas.session import AttachmentMeta, Session
from backend.utils.logger import log_event

SERVICE_QUESTIONNAIRE_PATH = "/users/api/enquiries/service-questionnaire"
TATVA_HTTP_HEADERS = {"User-Agent": "TatvaOps-Omni/1.0", "Accept": "application/json"}

_SUMMARY_SECTIONS: dict[str, str] = {
    "project-details": "PROJECT DETAILS",
    "description": "DESCRIPTION",
    "files": "FILES PROVIDED",
}

_TATVA_ENQUIRY_SUMMARY_LABELS: list[tuple[str, str]] = [
    ("projectOverview", "Project Overview"),
    ("scopeOfWork", "Scope of Work"),
    ("clientRequirements", "Client Requirements"),
    ("technicalSpecs", "Technical Specs"),
    ("timeline", "Timeline"),
    ("specialConsiderations", "Special Considerations"),
    ("estimatedScope", "Estimated Scope"),
]


def format_tatva_enquiry_summary_whatsapp(summary: dict[str, Any]) -> str:
    """Format Tatva API enquiry.summary object for WhatsApp confirmation."""
    lines: list[str] = []
    for key, label in _TATVA_ENQUIRY_SUMMARY_LABELS:
        value = summary.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if not text:
            continue
        lines.append(f"*{label}*\n{text}")
    return "\n\n".join(lines)


def _submit_key(step: dict) -> str:
    return str(step.get("submit_key") or step.get("field") or step.get("id") or "")


def _summary_item_id(submit_key: str) -> str:
    return submit_key.replace("_", "-")


def _summary_section_id(step: dict) -> str:
    stype = step.get("type")
    if stype in ("mcq", "multi_select"):
        return "project-details"
    if stype == "file_request":
        return "files"
    return "description"


def _summary_item_type(step: dict) -> str:
    stype = step.get("type")
    if stype == "file_request":
        return "file"
    if stype in ("mcq", "multi_select"):
        return "text"
    return "paragraph"


def _display_answer(step: dict, raw: Any, *, service_key: str) -> str:
    field = str(step.get("field") or "")
    if raw is None:
        return ""
    if isinstance(raw, list):
        parts = [_display_answer(step, item, service_key=service_key) for item in raw]
        return ", ".join(p for p in parts if p)

    raw_s = str(raw).strip()
    if not raw_s or raw_s.lower() in ("skipped", "skip", "none"):
        return ""

    if step.get("type") == "descriptive":
        return raw_s

    if step.get("type") in ("mcq", "multi_select"):
        for opt in step.get("options") or []:
            if str(opt.get("value", "")).strip() == raw_s:
                return str(opt.get("label") or raw_s).strip()
            if str(opt.get("label", "")).strip().lower() == raw_s.lower():
                return str(opt.get("label") or raw_s).strip()

    return display_label(field, raw_s, service_category=service_key)


def _file_answer_value(session: Session) -> str:
    if not session.attachments:
        return ""
    if len(session.attachments) == 1:
        return session.attachments[0].file_name
    return ", ".join(a.file_name for a in session.attachments)


def build_questionnaire_summary(session: Session, steps: list[dict]) -> list[dict]:
    """Build Tatva summary JSON grouped by question type."""
    service_key = session.service_category.value if session.service_category else ""
    ef = session.extracted_fields
    sections: dict[str, list[dict]] = {
        "project-details": [],
        "description": [],
        "files": [],
    }

    for step in steps:
        field = step.get("field")
        if not field:
            continue
        submit_key = _submit_key(step)
        if not submit_key:
            continue

        if step.get("type") == "file_request":
            value = _file_answer_value(session)
            if not value:
                continue
        else:
            raw = ef.get(field)
            value = _display_answer(step, raw, service_key=service_key)
            if not value:
                continue

        section_id = _summary_section_id(step)
        prompt = str(step.get("prompt") or "").strip()
        sections[section_id].append({
            "id": _summary_item_id(submit_key),
            "label": prompt_to_client_label(prompt) if prompt else field.replace("_", " ").title(),
            "value": value,
            "type": _summary_item_type(step),
        })

    result: list[dict] = []
    for section_id, title in _SUMMARY_SECTIONS.items():
        items = sections[section_id]
        if items:
            result.append({"id": section_id, "title": title, "items": items})
    return result


def build_questionnaire_form_fields(session: Session, steps: list[dict]) -> dict[str, str]:
    """Map question prompt text to human-readable answers for multipart form data."""
    service_key = session.service_category.value if session.service_category else ""
    ef = session.extracted_fields
    fields: dict[str, str] = {}

    for step in steps:
        field = step.get("field")
        prompt = str(step.get("prompt") or "").strip()
        if not field or not prompt:
            continue
        if step.get("type") == "file_request":
            continue

        raw = ef.get(field)
        value = _display_answer(step, raw, service_key=service_key)
        if value:
            fields[prompt] = value

    return fields


async def _download_attachment(meta: AttachmentMeta) -> Optional[tuple[bytes, str, str]]:
    """Return (bytes, filename, mime_type) for an attachment."""
    url = (meta.file_url or "").strip()
    if not url:
        return None

    try:
        if url.startswith("twilio:"):
            from backend.storage.media_store import download_twilio_media
            twilio_url = url.split(":", 1)[-1]
            data, ctype = await download_twilio_media(twilio_url)
            return data, meta.file_name, ctype or meta.mime_type or "application/octet-stream"

        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            response = await client.get(url)
            response.raise_for_status()
            ctype = response.headers.get("content-type") or meta.mime_type or "application/octet-stream"
            return response.content, meta.file_name, ctype
    except Exception as exc:
        await log_event(
            "API_ERROR",
            session_id="unknown",
            data={
                "api": "tatva_enquiry_submit",
                "error": f"attachment_download_failed: {exc}",
                "file_url": url[:120],
            },
        )
        return None


def _file_upload_prompts(steps: list[dict]) -> list[str]:
    return [
        str(step.get("prompt") or "").strip()
        for step in steps
        if step.get("type") == "file_request" and str(step.get("prompt") or "").strip()
    ]


async def submit_service_questionnaire(session: Session) -> Optional[dict[str, Any]]:
    """
    POST enquiry answers to Tatva service-questionnaire API.
    Uses tatva_user_id from session (register-phone) and dynamic questionnaire steps.
    Returns enquiry.summary from the API response on success.
    """
    if session.flow_state.get("tatva_enquiry_submitted"):
        stored = session.flow_state.get("tatva_enquiry_summary")
        return stored if isinstance(stored, dict) else None

    await register_tatva_user_for_session(session)
    user_id = str(session.extracted_fields.get("tatva_user_id") or "").strip()
    if not user_id:
        await log_event(
            "API_ERROR",
            session_id=session.session_id,
            data={"api": "tatva_enquiry_submit", "error": "missing_tatva_user_id"},
        )
        return False

    if not session.service_category:
        await log_event(
            "API_ERROR",
            session_id=session.session_id,
            data={"api": "tatva_enquiry_submit", "error": "missing_service_category"},
        )
        return False

    service_key = session.service_category.value
    service_id = str(
        session.flow_state.get("tatva_service_id")
        or get_service_mongo_id(session.service_category)
    )
    service_name = str(
        session.extracted_fields.get("tatva_service_name")
        or session.service_category.value.replace("_", " ").title()
    )

    steps = get_service_questionnaire_steps(session)
    if not steps:
        await log_event(
            "API_ERROR",
            session_id=session.session_id,
            data={"api": "tatva_enquiry_submit", "error": "no_questionnaire_steps"},
        )
        return False

    summary = build_questionnaire_summary(session, steps)
    question_fields = build_questionnaire_form_fields(session, steps)

    settings = get_settings()
    base_url = (settings.tatva_users_api_base_url or "").rstrip("/")
    if not base_url:
        await log_event(
            "API_ERROR",
            session_id=session.session_id,
            data={"api": "tatva_enquiry_submit", "error": "api_not_configured"},
        )
        return False

    url = f"{base_url}{SERVICE_QUESTIONNAIRE_PATH}"
    form_data: dict[str, str] = {
        "userId": user_id,
        "serviceId": service_id,
        "serviceName": service_name,
        "summary": json.dumps(summary, ensure_ascii=False),
        **question_fields,
    }

    files: list[tuple[str, tuple[str, bytes, str]]] = []
    file_prompts = _file_upload_prompts(steps)
    if session.attachments and file_prompts:
        file_field = file_prompts[0]
        for meta in session.attachments:
            downloaded = await _download_attachment(meta)
            if downloaded:
                data, fname, ctype = downloaded
                files.append((file_field, (fname, data, ctype)))

    await log_event(
        "TATVA_ENQUIRY_SUBMIT",
        session_id=session.session_id,
        data={
            "api": "tatva_enquiry_submit",
            "url": url,
            "user_id": user_id,
            "service_id": service_id,
            "service_name": service_name,
            "question_count": len(question_fields),
            "file_count": len(files),
            "summary_sections": len(summary),
        },
    )

    try:
        async with httpx.AsyncClient(timeout=60.0, headers=TATVA_HTTP_HEADERS) as client:
            if files:
                response = await client.post(url, data=form_data, files=files)
            else:
                response = await client.post(url, data=form_data)
            response.raise_for_status()
            payload = response.json()
    except httpx.HTTPStatusError as exc:
        body_preview = (exc.response.text or "")[:500]
        await log_event(
            "API_ERROR",
            session_id=session.session_id,
            data={
                "api": "tatva_enquiry_submit",
                "error": str(exc),
                "status_code": exc.response.status_code,
                "url": url,
                "response_body": body_preview,
            },
        )
        return False
    except Exception as exc:
        await log_event(
            "API_ERROR",
            session_id=session.session_id,
            data={
                "api": "tatva_enquiry_submit",
                "error": str(exc),
                "error_type": type(exc).__name__,
                "url": url,
            },
        )
        return False

    if not payload.get("success"):
        await log_event(
            "API_ERROR",
            session_id=session.session_id,
            data={
                "api": "tatva_enquiry_submit",
                "error": payload.get("message") or "unsuccessful_response",
                "url": url,
            },
        )
        return False

    session.flow_state["tatva_enquiry_submitted"] = True
    enquiry = (payload.get("data") or {}).get("enquiry") or {}
    tatva_summary = enquiry.get("summary") or {}
    if isinstance(tatva_summary, dict) and tatva_summary:
        session.flow_state["tatva_enquiry_summary"] = tatva_summary
    enquiry_id = enquiry.get("_id") or enquiry.get("id")
    if enquiry_id:
        session.flow_state["tatva_enquiry_id"] = str(enquiry_id)
    await log_event(
        "TATVA_ENQUIRY_SUBMIT_OK",
        session_id=session.session_id,
        data={
            "api": "tatva_enquiry_submit",
            "user_id": user_id,
            "service_id": service_id,
            "message": payload.get("message"),
            "enquiry_id": enquiry_id,
            "has_summary": bool(tatva_summary),
        },
    )
    return tatva_summary if isinstance(tatva_summary, dict) and tatva_summary else None

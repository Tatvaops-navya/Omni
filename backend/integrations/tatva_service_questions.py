"""
Fetch and transform Tatva service questionnaire from withtatva.ai API.
"""
from __future__ import annotations

from typing import Any, Optional

import httpx

from backend.config import get_settings
from backend.schemas.service import ServiceCategory, get_service_mongo_id
from backend.schemas.session import Session
from backend.utils.logger import log_event

SERVICE_QUESTIONS_PATH = "/users/api/service-questions"
TATVA_HTTP_HEADERS = {"User-Agent": "TatvaOps-Omni/1.0", "Accept": "application/json"}

TATVA_TYPE_MAP = {
    "mcq": "mcq",
    "description": "descriptive",
    "fileupload": "file_request",
}


def _field_for_question(question: dict[str, Any]) -> str:
    qtype = str(question.get("type") or "").lower()
    if qtype == "fileupload":
        return str(question.get("fileUploadField") or question.get("submitKey") or question.get("_id") or "")
    return str(question.get("submitKey") or question.get("_id") or "")


def transform_api_question(question: dict[str, Any]) -> dict[str, Any]:
    """Map a Tatva API question to the internal hybrid-flow step shape."""
    qtype = str(question.get("type") or "description").lower()
    internal_type = TATVA_TYPE_MAP.get(qtype, "descriptive")
    field = _field_for_question(question)
    prompt = str(question.get("questionText") or "").strip()

    step: dict[str, Any] = {
        "id": str(question.get("_id") or field),
        "stage": "service_questionnaire",
        "type": internal_type,
        "field": field,
        "prompt": prompt,
        "twilio_list_prompt": prompt,
        "tatva_question_id": str(question.get("_id") or ""),
        "submit_key": str(question.get("submitKey") or field),
        "display_order": int(question.get("displayOrder") or 0),
        "is_required": bool(question.get("isRequired", True)),
    }

    if internal_type == "mcq":
        options: list[dict[str, str]] = []
        for opt in question.get("options") or []:
            label = str(opt.get("label") or "").strip()
            value = str(opt.get("value") or label).strip()
            if label:
                options.append({"label": label, "value": value})
        step["options"] = options

    if internal_type == "file_request":
        step["allowed_file_types"] = list(question.get("allowedFileTypes") or [])
        step["max_files"] = question.get("maxFiles")
        step["max_file_size_mb"] = question.get("maxFileSizeMb")
        step["allow_multiple"] = bool(question.get("allowMultiple", False))

    if not question.get("isRequired", True):
        step["optional"] = True

    return step


def build_steps_from_api_questions(questions: list[dict[str, Any]]) -> list[dict]:
    """Sort active questions by displayOrder and enrich MCQ steps for WhatsApp."""
    from backend.intelligence.qualification_builder import _enrich_mcq_step

    active = [q for q in questions if q.get("isActive", True)]
    active.sort(key=lambda q: int(q.get("displayOrder") or 0))
    steps = [transform_api_question(q) for q in active if _field_for_question(q)]
    return [_enrich_mcq_step(s) if s.get("type") == "mcq" else s for s in steps]


def required_fields_from_steps(steps: list[dict]) -> list[str]:
    return [str(s["field"]) for s in steps if s.get("field") and not s.get("optional")]


def get_cached_steps(session: Session) -> list[dict]:
    return list((session.flow_state or {}).get("dynamic_questionnaire_steps") or [])


def sync_questionnaire_state(session: Session, steps: list[dict], *, source: str) -> None:
    """Persist fetched steps and derived required-field list on the session."""
    required = required_fields_from_steps(steps)
    session.flow_state["dynamic_questionnaire_steps"] = steps
    session.flow_state["service_questionnaire_required_fields"] = required
    session.flow_state["questionnaire_source"] = source
    session.flow_state["pending_questions"] = [
        f for f in required if f not in session.flow_state.get("completed_questions", [])
    ]


async def fetch_service_questions(
    service_id: str,
    *,
    session_id: str = "unknown",
) -> Optional[dict[str, Any]]:
    settings = get_settings()
    base_url = (settings.tatva_users_api_base_url or "").rstrip("/")
    if not base_url:
        await log_event(
            "API_ERROR",
            session_id=session_id,
            data={"api": "tatva_service_questions", "error": "api_not_configured"},
        )
        return None

    url = f"{base_url}{SERVICE_QUESTIONS_PATH}"
    await log_event(
        "TATVA_SERVICE_QUESTIONS_FETCH",
        session_id=session_id,
        data={
            "api": "tatva_service_questions",
            "url": url,
            "service_id": service_id,
        },
    )
    try:
        async with httpx.AsyncClient(timeout=15.0, headers=TATVA_HTTP_HEADERS) as client:
            response = await client.get(url, params={"serviceId": service_id})
            response.raise_for_status()
            payload = response.json()
    except httpx.HTTPStatusError as exc:
        body_preview = (exc.response.text or "")[:500]
        await log_event(
            "API_ERROR",
            session_id=session_id,
            data={
                "api": "tatva_service_questions",
                "error": str(exc),
                "status_code": exc.response.status_code,
                "service_id": service_id,
                "url": url,
                "response_body": body_preview,
            },
        )
        return None
    except Exception as exc:
        await log_event(
            "API_ERROR",
            session_id=session_id,
            data={
                "api": "tatva_service_questions",
                "error": str(exc),
                "error_type": type(exc).__name__,
                "service_id": service_id,
                "url": url,
            },
        )
        return None

    if not payload.get("success"):
        await log_event(
            "API_ERROR",
            session_id=session_id,
            data={
                "api": "tatva_service_questions",
                "error": payload.get("message") or "unsuccessful_response",
                "service_id": service_id,
                "url": url,
                "response_success": payload.get("success"),
            },
        )
        return None

    data = payload.get("data") or {}
    questions = data.get("questions") or []
    await log_event(
        "TATVA_SERVICE_QUESTIONS_OK",
        session_id=session_id,
        data={
            "api": "tatva_service_questions",
            "service_id": service_id,
            "service_name": data.get("serviceName"),
            "question_count": len(questions),
            "url": url,
        },
    )

    return payload


def _static_fallback_steps(category: ServiceCategory) -> list[dict]:
    from backend.intelligence.qualification_builder import _service_questionnaire_steps

    return _service_questionnaire_steps(category)


async def load_questionnaire_for_session(session: Session, category: ServiceCategory) -> list[dict]:
    """
    Fetch Tatva service questions for the selected category and cache on session.
    Falls back to static flows/*.json when the API is unavailable.
    """
    service_id = get_service_mongo_id(category)
    payload = await fetch_service_questions(service_id, session_id=session.session_id)

    if payload:
        data = payload.get("data") or {}
        questions = data.get("questions") or []
        steps = build_steps_from_api_questions(questions)
        if steps:
            sync_questionnaire_state(session, steps, source="tatva_api")
            session.flow_state["tatva_service_id"] = str(data.get("serviceId") or service_id)
            if data.get("serviceName"):
                session.extracted_fields["tatva_service_name"] = data["serviceName"]
            await log_event(
                "SERVICE_QUESTIONS_LOADED",
                session_id=session.session_id,
                data={
                    "service_id": service_id,
                    "service_category": category.value,
                    "question_count": len(steps),
                    "fields": [s.get("field") for s in steps],
                    "source": "tatva_api",
                },
            )
            return steps
        await log_event(
            "API_ERROR",
            session_id=session.session_id,
            data={
                "api": "tatva_service_questions",
                "error": "api_returned_no_usable_questions",
                "service_id": service_id,
                "service_category": category.value,
                "raw_question_count": len(questions),
            },
        )

    await log_event(
        "API_ERROR",
        session_id=session.session_id,
        data={
            "api": "tatva_service_questions",
            "error": "falling_back_to_static_json",
            "service_id": service_id,
            "service_category": category.value,
            "fallback_file": f"{category.value}.json",
        },
    )
    steps = _static_fallback_steps(category)
    sync_questionnaire_state(session, steps, source="static_fallback")
    await log_event(
        "SERVICE_QUESTIONS_LOADED",
        session_id=session.session_id,
        data={
            "service_id": service_id,
            "service_category": category.value,
            "question_count": len(steps),
            "fields": [s.get("field") for s in steps],
            "source": "static_fallback",
        },
    )
    return steps


async def ensure_questionnaire_loaded(session: Session) -> list[dict]:
    """
    Load Tatva questionnaire when missing or still on static fallback.
    Re-fetches from the API so resumed sessions and transient API failures recover.
    """
    category = session.service_category
    if not category:
        return []

    cached = get_cached_steps(session)
    source = (session.flow_state or {}).get("questionnaire_source")
    if cached and source == "tatva_api":
        return cached

    return await load_questionnaire_for_session(session, category)

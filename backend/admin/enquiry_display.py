"""Human-readable requirement summaries for admin enquiry views."""
from __future__ import annotations

from typing import Any

from backend.intelligence.display_labels import display_label, prompt_to_client_label
from backend.integrations.tatva_enquiry_submit import _display_answer
from backend.integrations.tatva_service_questions import build_steps_from_api_questions

_QUESTIONNAIRE_FIELD_PREFIXES = ("service_q", "order_", "file_order_")
_SKIP_SUMMARY_FIELDS = frozenset({
    "tatva_service_name",
    "assigned_consultant",
    "active_consultant",
    "service_category",
})

_steps_cache: dict[str, list[dict]] = {}


def _is_questionnaire_field(field: str) -> bool:
    if field in _SKIP_SUMMARY_FIELDS:
        return False
    return any(field.startswith(prefix) for prefix in _QUESTIONNAIRE_FIELD_PREFIXES) or field == "attachments"


def _field_sort_key(field: str) -> tuple[int, str]:
    for prefix in ("order_", "file_order_", "service_q"):
        if field.startswith(prefix):
            suffix = field[len(prefix):]
            try:
                return (int(suffix), field)
            except ValueError:
                return (999, field)
    return (999, field)


def _label_map_from_steps(steps: list[dict]) -> dict[str, str]:
    labels: dict[str, str] = {}
    for step in steps:
        field = str(step.get("field") or "")
        prompt = str(step.get("prompt") or "").strip()
        if field and prompt:
            labels[field] = prompt_to_client_label(prompt)
    return labels


def build_requirements_summary(
    extracted_fields: dict[str, Any],
    *,
    service_category: str = "",
    steps: list[dict] | None = None,
) -> list[dict[str, str]]:
    """Map questionnaire answers to short labels + readable values."""
    if not extracted_fields:
        return []

    cached = extracted_fields.get("_requirements_summary")
    if isinstance(cached, list) and cached:
        return [
            {"label": str(item.get("label") or ""), "value": str(item.get("value") or "")}
            for item in cached
            if str(item.get("label") or "").strip() and str(item.get("value") or "").strip()
        ]

    label_map = extracted_fields.get("_questionnaire_labels")
    if not isinstance(label_map, dict):
        label_map = {}
    if steps and not label_map:
        label_map = _label_map_from_steps(steps)

    items: list[dict[str, str]] = []
    seen_fields: set[str] = set()

    step_by_field: dict[str, dict] = {}
    if steps:
        for step in steps:
            field = str(step.get("field") or "")
            if field:
                step_by_field[field] = step

    questionnaire_fields = [
        f for f in extracted_fields
        if _is_questionnaire_field(f) and not str(f).startswith("_")
    ]
    questionnaire_fields.sort(key=_field_sort_key)

    for field in questionnaire_fields:
        if field in seen_fields:
            continue
        raw = extracted_fields.get(field)
        if raw is None or str(raw).strip().lower() in ("", "skip", "skipped", "none"):
            continue

        step = step_by_field.get(field)
        label = str(label_map.get(field) or "").strip()
        if not label and step:
            prompt = str(step.get("prompt") or "").strip()
            label = prompt_to_client_label(prompt) if prompt else _fallback_field_label(field)
        if not label:
            label = _fallback_field_label(field)

        if step and step.get("type") == "file_request":
            value = str(raw).strip()
        elif step:
            value = _display_answer(step, raw, service_key=service_category)
        else:
            value = display_label(field, raw, service_category=service_category)

        if not value or value == "—":
            value = str(raw).strip()
        if not value:
            continue

        seen_fields.add(field)
        items.append({"label": label, "value": value})

    return items


def _fallback_field_label(field: str) -> str:
    if field.startswith("file_order_"):
        return "Supporting files"
    if field.startswith("order_"):
        return f"Question {field.replace('order_', '')}"
    if field.startswith("service_q"):
        return f"Requirement {field.replace('service_q', '')}"
    return field.replace("_", " ").strip().title()


def snapshot_requirements_for_session(session) -> dict[str, Any]:
    """Persist labels + summary on the enquiry for stable admin display."""
    from backend.integrations.tatva_service_questions import get_cached_steps, questionnaire_cache_matches_session
    from backend.intelligence.qualification_builder import get_service_questionnaire_steps

    service_key = session.service_category.value if session.service_category else ""
    steps: list[dict] = []
    if questionnaire_cache_matches_session(session):
        steps = get_cached_steps(session)
    if not steps and session.service_category:
        steps = get_service_questionnaire_steps(session)

    fields = dict(session.extracted_fields or {})
    if steps:
        fields["_questionnaire_labels"] = _label_map_from_steps(steps)
    summary = build_requirements_summary(
        fields,
        service_category=service_key,
        steps=steps or None,
    )
    if summary:
        fields["_requirements_summary"] = summary
    return fields


async def steps_for_service_category(service_category: str) -> list[dict]:
    """Load Tatva questionnaire steps for a service (cached per process)."""
    if not service_category:
        return []
    if service_category in _steps_cache:
        return _steps_cache[service_category]

    from backend.schemas.service import ServiceCategory, get_service_mongo_id
    from backend.integrations.tatva_service_questions import fetch_service_questions

    try:
        category = ServiceCategory(service_category)
    except ValueError:
        _steps_cache[service_category] = []
        return []

    service_id = get_service_mongo_id(category)
    payload = await fetch_service_questions(service_id, session_id="admin_enquiries")
    if not payload:
        from backend.intelligence.qualification_builder import _service_questionnaire_steps
        steps = _service_questionnaire_steps(category)
    else:
        questions = (payload.get("data") or {}).get("questions") or []
        steps = build_steps_from_api_questions(questions)
    _steps_cache[service_category] = steps
    return steps


async def enrich_enquiry_row(row: dict[str, Any]) -> dict[str, Any]:
    """Attach requirements_summary for admin UI."""
    fields = dict(row.get("extracted_fields") or {})
    service_category = str(row.get("service_category") or fields.get("service_category") or "")
    steps = None
    if not fields.get("_requirements_summary"):
        steps = await steps_for_service_category(service_category)
    summary = build_requirements_summary(
        fields,
        service_category=service_category,
        steps=steps or None,
    )
    row["requirements_summary"] = summary
    return row


async def enrich_enquiries(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Batch-enrich enquiries with human-readable requirement summaries."""
    enriched: list[dict[str, Any]] = []
    for row in rows:
        enriched.append(await enrich_enquiry_row(dict(row)))
    return enriched

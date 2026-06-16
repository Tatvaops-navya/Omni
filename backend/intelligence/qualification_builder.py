"""
Static, deterministic qualification builder for AVA flow.
"""
from __future__ import annotations
import json
from pathlib import Path
from typing import Any

from backend.schemas.service import ServiceCategory
from backend.intelligence.stage_engine import STAGE_TITLES
from backend.intelligence.display_labels import display_label

FLOW_FILE_BY_SERVICE: dict[ServiceCategory, str] = {
    ServiceCategory.RESIDENTIAL_CONSTRUCTION: "residential_construction.json",
    ServiceCategory.HOME_INTERIORS: "home_interiors.json",
    ServiceCategory.PAINTING_WATERPROOFING: "painting_waterproofing.json",
    ServiceCategory.ELECTRICAL: "electrical.json",
    ServiceCategory.PLUMBING: "plumbing.json",
    ServiceCategory.SOLAR: "solar.json",
    ServiceCategory.HOME_AUTOMATION: "home_automation.json",
    ServiceCategory.EVENT_MANAGEMENT: "event_management.json",
    ServiceCategory.PROPERTY_DEVELOPMENT: "property_development.json",
    ServiceCategory.FARM_INFRASTRUCTURE: "farm_infrastructure.json",
    ServiceCategory.IRRIGATION_AUTOMATION: "irrigation_automation.json",
}

# Back-compat alias
SECTION_TITLES = STAGE_TITLES

# Dedicated contact-time list (Morning/Afternoon/Evening/Night).
CONTACT_TIME_TWILIO_CONTENT_SID = "HX4e36328276831fc79aa5feb83f0b86a4"


def _mcq_option_count(step: dict) -> int:
    return len([o for o in step.get("options", []) if str(o.get("value", "")).lower() != "__other__"])


def _variable_mcq_list_sid(option_count: int) -> str | None:
    """Fully variable {{prompt}} + option rows — safe for any service MCQ."""
    from backend.config import get_settings
    cfg = get_settings()
    fallback = (cfg.twilio_whatsapp_interactive_content_sid or "").strip()
    if option_count == 5:
        sid = (cfg.twilio_mcq_list_5_content_sid or fallback).strip()
    elif option_count == 1:
        sid = (cfg.twilio_mcq_list_1_content_sid or "").strip()
    elif option_count == 2:
        # Never use the 4-row template for 2 options — empty rows show {{option_3_label}} placeholders.
        sid = (cfg.twilio_mcq_list_2_content_sid or "").strip()
    elif option_count == 3:
        sid = (cfg.twilio_mcq_list_3_content_sid or "").strip()
    elif option_count == 4:
        sid = (cfg.twilio_mcq_list_4_content_sid or fallback).strip()
    else:
        sid = ""
    return sid or None


def _resolve_mcq_twilio_sid(step: dict) -> str | None:
    """
    Twilio list template for MCQ steps.
    - Flow JSON may define a service-specific SID (home_interiors, electrical, …).
    - Contact time uses its dedicated template.
    - Other service_q steps use variable 2/3/4/5-row MCQ templates (Choose option).
    """
    explicit = step.get("twilio_content_sid")
    if explicit:
        return str(explicit)
    field = str(step.get("field", ""))
    if field == "preferred_contact_time":
        return CONTACT_TIME_TWILIO_CONTENT_SID
    if field == "willing_to_create_project":
        return _variable_mcq_list_sid(2)
    if (
        field.startswith("service_q")
        or field.startswith("order_")
        or field.startswith("file_order_")
        or field.startswith("__edit_")
        or field == "__final_review__"
    ):
        return _variable_mcq_list_sid(_mcq_option_count(step))
    return None


def _attach_mcq_list_delivery(out: dict, sid: str, step: dict) -> dict:
    out["twilio_content_sid"] = sid
    out["require_content_variables"] = True
    field = str(step.get("field", ""))
    if step.get("twilio_list_prompt"):
        out["twilio_list_prompt"] = str(step["twilio_list_prompt"]).strip()
    else:
        out["twilio_list_prompt"] = str(step.get("prompt") or "").strip()
    count = _mcq_option_count(step)
    if (
        sid == CONTACT_TIME_TWILIO_CONTENT_SID
        or field.startswith("service_q")
        or field.startswith("order_")
        or field.startswith("file_order_")
        or field.startswith("__edit_")
        or field == "__final_review__"
        or field == "willing_to_create_project"
    ):
        out["twilio_list_slots"] = count
        if sid != CONTACT_TIME_TWILIO_CONTENT_SID:
            out["twilio_list_use_descriptions"] = True
    return out


def enrich_mcq_step_for_whatsapp(step: dict) -> dict:
    """Public helper — attach Twilio list-picker metadata when configured."""
    return _enrich_mcq_step(step)


def _enrich_mcq_step(step: dict) -> dict:
    """Attach shared WhatsApp list template when MCQ should use Choose option."""
    if step.get("type") != "mcq" or step.get("force_plain_mcq"):
        return step
    sid = _resolve_mcq_twilio_sid(step)
    if not sid:
        return step
    return _attach_mcq_list_delivery(dict(step), sid, step)


def _build_service_mcq_step(step: dict, *, field: str, step_id: str) -> dict:
    sid = _resolve_mcq_twilio_sid(step)
    out = {
        "id": step_id,
        "stage": "service_questionnaire",
        "type": "mcq",
        "field": field,
        "prompt": step["prompt"],
        "options": step.get("options", []),
    }
    if sid:
        _attach_mcq_list_delivery(out, sid, step)
    return out


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _load_service_flow(category: ServiceCategory) -> list[dict]:
    flow_dir = _repo_root() / "backend" / "intelligence" / "flows"
    file_name = FLOW_FILE_BY_SERVICE[category]
    path = flow_dir / file_name
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _service_questionnaire_steps(category: ServiceCategory) -> list[dict]:
    flow = _load_service_flow(category)
    by_field = {str(s.get("field")): s for s in flow if s.get("field")}

    def _require_step(field: str, expected_type: str) -> dict:
        step = by_field.get(field)
        if not step:
            raise RuntimeError(f"Missing required step '{field}' for service '{category.value}'.")
        if step.get("type") != expected_type:
            raise RuntimeError(
                f"Invalid step type for '{field}' in service '{category.value}'. "
                f"Expected '{expected_type}', got '{step.get('type')}'."
            )
        prompt = str(step.get("prompt") or "").strip()
        if not prompt:
            raise RuntimeError(f"Missing prompt for step '{field}' in service '{category.value}'.")
        return step

    s1 = _require_step("service_q1", "mcq")
    s2 = _require_step("service_q2", "mcq")
    s3 = _require_step("service_q3", "mcq")
    s4 = _require_step("service_q4", "descriptive")
    s5 = _require_step("attachments", "file_request")

    q1 = _build_service_mcq_step(s1, field="service_q1", step_id="service_q1")
    q2 = _build_service_mcq_step(s2, field="service_q2", step_id="service_q2")
    q3 = _build_service_mcq_step(s3, field="service_q3", step_id="service_q3")
    q4 = {
        "id": "service_q4",
        "stage": "service_questionnaire",
        "type": "descriptive",
        "field": "service_q4",
        "prompt": s4["prompt"],
    }
    q5 = {
        "id": "service_q5",
        "stage": "service_questionnaire",
        "type": "file_request",
        "field": "attachments",
        "prompt": s5["prompt"],
    }
    return [q1, q2, q3, q4, q5]


def get_service_questionnaire_steps(session) -> list[dict]:
    """Return cached Tatva API steps when present, else static JSON fallback."""
    from backend.integrations.tatva_service_questions import get_cached_steps

    cached = get_cached_steps(session)
    if cached:
        return cached
    if session.service_category:
        return _service_questionnaire_steps(session.service_category)
    return []


def build_client_details_steps() -> list[dict]:
    return [
        {"id": "cd_name", "stage": "client_details", "type": "descriptive", "field": "client_name", "prompt": "What is your full name?"},
        {"id": "cd_city", "stage": "client_details", "type": "descriptive", "field": "city", "prompt": "Which city are you located in?"},
        {"id": "cd_property_loc", "stage": "client_details", "type": "descriptive", "field": "property_location", "prompt": "Where is your property located? (City, Locality)"},
        {"id": "cd_email", "stage": "client_details", "type": "descriptive", "field": "email", "prompt": "Email address (optional).", "optional": True},
        _enrich_mcq_step({
            "id": "cd_contact_time",
            "stage": "client_details",
            "type": "mcq",
            "field": "preferred_contact_time",
            "prompt": "Preferred contact time? (only if Needed)",
            "options": [
                {"label": "Morning", "value": "morning"},
                {"label": "Afternoon", "value": "afternoon"},
                {"label": "Evening", "value": "evening"},
                {"label": "Night", "value": "night"},
            ],
        }),
        _enrich_mcq_step({
            "id": "cd_create_project",
            "stage": "client_details",
            "type": "mcq",
            "field": "willing_to_create_project",
            "prompt": (
                "Would you like to proceed with creating your project? "
                "Once created, a dedicated Relationship Manager will guide you through every step."
            ),
            "twilio_list_prompt": "Would you like to proceed with creating your project?",
            "options": [
                {"label": "Yes, Create My Project", "value": "yes"},
                {"label": "No, I'm Just Exploring", "value": "no"},
            ],
        }),
    ]


def get_steps_for_stage(session, stage: str) -> list[dict]:
    """Steps for exactly one stage."""
    if stage == "client_details":
        return build_client_details_steps()
    if stage == "service_selection":
        return []
    if stage == "consultant_assignment":
        return []
    if stage != "service_questionnaire" or not session.service_category:
        return []
    return get_service_questionnaire_steps(session)


def build_qualification_flow(category: ServiceCategory) -> list[dict]:
    """Full ordered flow for deterministic AVA onboarding."""
    steps: list[dict] = []
    steps.extend(build_client_details_steps())
    steps.extend(_service_questionnaire_steps(category))
    return steps


def required_fields_for_summary(session) -> list[str]:
    from backend.intelligence.stage_engine import required_fields_for_summary as _rfs
    return _rfs(session)


def is_qualification_complete(session) -> bool:
    from backend.intelligence.stage_engine import is_qualification_complete as _iqc
    return _iqc(session)


def qualification_completion_pct(session) -> int:
    from backend.intelligence.stage_engine import qualification_completion_pct as _pct
    return _pct(session)


def _humanize(field: str, value: Any, *, service_category: str = "") -> str:
    return display_label(field, value, service_category=service_category)


FINAL_REVIEW_ACTION_OPTIONS = [
    {"label": "Confirm & Submit", "value": "confirm_submit"},
]


def final_review_action_step() -> dict:
    return {
        "id": "final_review_actions",
        "type": "mcq",
        "field": "__final_review__",
        "prompt": "Does everything look correct?",
        "twilio_list_prompt": "Does everything look correct?",
        "options": list(FINAL_REVIEW_ACTION_OPTIONS),
    }


def prepare_final_review_outbound(session) -> dict:
    """Attach WhatsApp list-picker metadata for Confirm & Submit."""
    step = _enrich_mcq_step(final_review_action_step())
    session.flow_state["final_review_outbound_step"] = step
    return step


def get_final_review_outbound_step(session) -> dict:
    stored = (session.flow_state or {}).get("final_review_outbound_step")
    if stored:
        return _enrich_mcq_step(dict(stored))
    return prepare_final_review_outbound(session)


def format_final_review(session, *, include_footer: bool | None = None) -> str:
    """Structured preview before summary generation."""
    from backend.intelligence.stage_engine import can_enter_final_review, missing_fields_report
    if not can_enter_final_review(session):
        missing = missing_fields_report(session)
        return (
            "We still need a few details before your summary:\n"
            + "\n".join(f"• {m.replace('_', ' ')}" for m in missing[:8])
            + "\n\nPlease answer the current question to continue."
        )

    ef = session.extracted_fields
    from backend.intelligence.consultants.registry import get_service_label
    svc = get_service_label(session.service_category) if session.service_category else "—"
    service_key = session.service_category.value if session.service_category else ""
    consultant = session.flow_state.get("assigned_consultant") or session.active_consultant or "—"

    blocks = [
        "Here is a quick review of your enquiry:",
        "",
        "*Client Details*",
        f"- Name: {_humanize('client_name', ef.get('client_name'), service_category=service_key)}",
        f"- Phone: {_humanize('phone_number', ef.get('phone_number'), service_category=service_key)}",
        f"- Location: {_humanize('city', ef.get('city'), service_category=service_key)}",
        f"- Property location: {_humanize('property_location', ef.get('property_location'), service_category=service_key)}",
        f"- Preferred contact time: {_humanize('preferred_contact_time', ef.get('preferred_contact_time'), service_category=service_key)}",
        f"- Willing to create project: {_humanize('willing_to_create_project', ef.get('willing_to_create_project'), service_category=service_key)}",
        f"- Email: {_humanize('email', ef.get('email'), service_category=service_key)}",
        "",
        "*Service Brief*",
        f"- Service: {_humanize('service_category', service_key or svc, service_category=service_key)}",
        f"- Specialist: {_humanize('assigned_consultant', consultant, service_category=service_key)}",
        "",
        "*Requirements Shared*",
    ]
    blocks.extend(_format_requirements_review(session, service_key=service_key))
    blocks.extend([
        "",
        "*Files*",
        f"- {_format_attachments_review(session, service_key=service_key)}",
    ])
    if include_footer is None:
        include_footer = not (session.flow_state or {}).get("final_review_outbound_step")
    if include_footer:
        blocks.extend([
            "",
            "Does everything look correct? Reply *Confirm & Submit* to finish.",
        ])
    return "\n".join(blocks)


def _question_review_label(step: dict) -> str:
    prompt = str(step.get("prompt") or "").strip()
    if prompt:
        text = prompt.split("\n")[0].strip()
    else:
        text = str(step.get("field") or "").replace("_", " ").title()
    return text.rstrip("?. ").strip()


def _requirement_review_line(question: str, answer: str) -> str:
    """Single requirement row: Question - Answer (no trailing ? or colon clutter)."""
    q = (question or "").strip().rstrip("?. ").strip()
    a = (answer or "—").strip()
    return f"- {q} - {a}"


def _format_requirements_review(session, *, service_key: str = "") -> list[str]:
    ef = session.extracted_fields
    lines: list[str] = []
    for step in get_service_questionnaire_steps(session):
        field = step.get("field")
        stype = step.get("type")
        if not field or stype == "file_request":
            continue
        label = _question_review_label(step)
        value = _humanize(field, ef.get(field), service_category=service_key)
        lines.append(_requirement_review_line(label, value))
    if lines:
        return lines
    return [
        _requirement_review_line("Requirement 1", _humanize("service_q1", ef.get("service_q1"), service_category=service_key)),
        _requirement_review_line("Requirement 2", _humanize("service_q2", ef.get("service_q2"), service_category=service_key)),
        _requirement_review_line("Requirement 3", _humanize("service_q3", ef.get("service_q3"), service_category=service_key)),
        _requirement_review_line("Additional notes", _humanize("service_q4", ef.get("service_q4"), service_category=service_key)),
    ]


def _format_attachments_review(session, *, service_key: str = "") -> str:
    ef = session.extracted_fields
    for step in get_service_questionnaire_steps(session):
        if step.get("type") != "file_request":
            continue
        field = step.get("field")
        if field:
            return _humanize(field, ef.get(field, "none"), service_category=service_key)
    return _humanize("attachments", ef.get("attachments", "none"), service_category=service_key)


# Alias
format_confirmation_recap = format_final_review

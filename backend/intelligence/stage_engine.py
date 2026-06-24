"""
Deterministic stage-based qualification workflow.
Stages advance ONLY when every required field has a valid value.
"""
from __future__ import annotations
import re
from typing import Any, Optional

from backend.schemas.service import ServiceCategory
from backend.schemas.session import Session, ConversationStage

# Accepts common email formats across providers and custom domains (gmail, outlook, company.co.in, etc.).
_EMAIL_ADDRESS_RE = re.compile(
    r"^[^\s@]+@[^\s@]+\.[^\s@]{2,}$",
    re.IGNORECASE,
)

STAGE_ORDER: list[str] = [
    "ava_intro",
    "client_details",
    "service_selection",
    "consultant_assignment",
    "service_questionnaire",
    "final_review",
]

STAGE_TITLES: dict[str, str] = {
    "ava_intro": "Welcome to TatvaOps",
    "client_details": "Let us start with a few quick details",
    "service_selection": "Great, now choose the service you need",
    "consultant_assignment": "Connecting you with the right specialist",
    "service_questionnaire": "Thanks, now let us understand your requirements",
    "final_review": "Review your enquiry",
}

STAGE_REQUIRED_FIELDS: dict[str, list[str]] = {
    "ava_intro": ["ava_intro_shown"],
    "client_details": [
        "client_name", "phone_number", "city", "property_location",
        "willing_to_create_project",
    ],
    "service_selection": ["service_category"],
    "consultant_assignment": ["assigned_consultant"],
    "service_questionnaire": [
        "service_q1", "service_q2", "service_q3", "service_q4", "attachments",
    ],
    "final_review": [],
}

OPTIONAL_FIELDS = frozenset({"email", "req_functional_needs", "req_inspiration_notes", "special_notes_extra"})

INVALID_VALUES = frozenset({"", "—", "-", "null", "none", "undefined", "n/a", "na", "skip", "skipped"})


def _is_file_upload_field(field: str) -> bool:
    return field == "attachments" or field.startswith("file_")


def required_fields_for_stage(session: Session, stage: str) -> list[str]:
    if stage == "service_questionnaire":
        custom = (session.flow_state or {}).get("service_questionnaire_required_fields")
        if custom:
            return list(custom)
    return list(STAGE_REQUIRED_FIELDS.get(stage, []))


def is_valid_email_address(value: Any) -> bool:
    """True when value looks like a standard email address on any domain."""
    s = str(value or "").strip()
    if not s or s.count("@") != 1:
        return False
    if ".." in s or s.startswith("@") or s.endswith("@"):
        return False
    local, domain = s.rsplit("@", 1)
    if not local or not domain or "." not in domain:
        return False
    if domain.startswith(".") or domain.endswith("."):
        return False
    return _EMAIL_ADDRESS_RE.fullmatch(s) is not None


def is_valid_gmail_address(value: Any) -> bool:
    """Backward-compatible alias — accepts any valid email address."""
    return is_valid_email_address(value)


def is_valid_field_value(value: Any, *, field: str = "") -> bool:
    if value is None:
        return False
    if field in OPTIONAL_FIELDS and value in ("", None):
        return True
    if field == "email":
        s = str(value).strip()
        if not s:
            return True
        return is_valid_email_address(s)
    if field == "attachments" or _is_file_upload_field(field):
        if str(value).lower() in ("skipped", "skip", "none"):
            return True
    if isinstance(value, list):
        return len(value) > 0
    s = str(value).strip()
    if not s:
        return False
    if s.lower() in INVALID_VALUES:
        return False
    return True


def field_is_complete(session: Session, field: str) -> bool:
    if field not in session.completed_fields:
        return False
    val = session.extracted_fields.get(field)
    return is_valid_field_value(val, field=field)


def ensure_flow_state(session: Session) -> None:
    fs = session.flow_state
    fs.setdefault("current_stage", "ava_intro")
    fs.setdefault("completed_stages", [])
    fs.setdefault("pending_fields", [])
    fs.setdefault("current_question", None)
    fs.setdefault("selected_service", session.service_category.value if session.service_category else "")
    fs.setdefault("assigned_consultant", session.active_consultant or "")
    fs.setdefault("completed_questions", [])
    fs.setdefault("pending_questions", [])
    fs.setdefault("answers", {})
    fs.setdefault("attachments", [])


def sync_pending_fields(session: Session) -> list[str]:
    ensure_flow_state(session)
    stage = fs_current_stage(session)
    if stage == "final_review":
        session.flow_state["pending_fields"] = []
        return []
    required = required_fields_for_stage(session, stage)
    pending = [f for f in required if not field_is_complete(session, f)]
    session.flow_state["pending_fields"] = pending
    return pending


def fs_current_stage(session: Session) -> str:
    ensure_flow_state(session)
    return session.flow_state.get("current_stage", "ava_intro")


def set_current_question(session: Session, field: Optional[str]) -> None:
    session.flow_state["current_question"] = field


def is_stage_complete(session: Session, stage: str) -> bool:
    if stage == "service_selection":
        if not session.service_category:
            return False
        return field_is_complete(session, "service_category")
    for f in required_fields_for_stage(session, stage):
        if not field_is_complete(session, f):
            return False
    return True


def first_incomplete_stage(session: Session) -> str:
    for stage in STAGE_ORDER:
        if stage == "final_review":
            break
        if not is_stage_complete(session, stage):
            return stage
    return "final_review"


def can_enter_final_review(session: Session) -> bool:
    """All 9 qualification stages must have valid required data."""
    for stage in STAGE_ORDER:
        if stage == "final_review":
            break
        if not is_stage_complete(session, stage):
            return False
    return session.service_category is not None


def all_qualification_stages_complete(session: Session) -> bool:
    return can_enter_final_review(session)


def is_in_final_review(session: Session) -> bool:
    return fs_current_stage(session) == "final_review" and can_enter_final_review(session)


def mark_stage_complete(session: Session, stage: str) -> None:
    if not is_stage_complete(session, stage):
        return
    ensure_flow_state(session)
    completed: list[str] = session.flow_state.setdefault("completed_stages", [])
    if stage not in completed:
        completed.append(stage)


def reconcile_session(session: Session) -> str:
    """
    Align current_stage / completed_stages with actual valid field data.
  Prevents premature final review and fixes stale completed_fields.
    """
    ensure_flow_state(session)

    if session.flow_state.get("project_declined"):
        session.flow_state["current_stage"] = "client_details"
        session.flow_state.pop("current_step_id", None)
        set_current_question(session, None)
        sync_pending_fields(session)
        return fs_current_stage(session)

    session.completed_fields = [
        f for f in session.completed_fields if field_is_complete(session, f)
    ]

    rebuilt_stages: list[str] = []
    for stage in STAGE_ORDER:
        if stage == "final_review":
            break
        if is_stage_complete(session, stage):
            rebuilt_stages.append(stage)

    session.flow_state["completed_stages"] = rebuilt_stages

    if can_enter_final_review(session):
        session.flow_state["current_stage"] = "final_review"
    else:
        session.flow_state["current_stage"] = first_incomplete_stage(session)
        if session.conversation_stage == ConversationStage.CONFIRMATION:
            session.conversation_stage = ConversationStage.DETAIL_COLLECTION

    session.flow_state.pop("current_step_id", None)
    sync_pending_fields(session)
    return fs_current_stage(session)


def maybe_advance_current_stage(session: Session) -> str:
    """Advance at most ONE stage when the current stage is fully valid."""
    reconcile_session(session)
    current = fs_current_stage(session)
    if current == "final_review":
        return current
    if not is_stage_complete(session, current):
        return current

    mark_stage_complete(session, current)
    try:
        idx = STAGE_ORDER.index(current)
    except ValueError:
        return current

    if idx + 1 >= len(STAGE_ORDER):
        return current

    nxt = STAGE_ORDER[idx + 1]
    if nxt == "final_review":
        if can_enter_final_review(session):
            session.flow_state["current_stage"] = "final_review"
            session.conversation_stage = ConversationStage.CONFIRMATION
        else:
            session.flow_state["current_stage"] = first_incomplete_stage(session)
        sync_pending_fields(session)
        return fs_current_stage(session)

    session.flow_state["current_stage"] = nxt
    session.flow_state.pop("current_step_id", None)
    session.flow_state.pop("last_stage_shown", None)
    sync_pending_fields(session)
    return nxt


def try_complete_and_advance(session: Session) -> str:
    return maybe_advance_current_stage(session)


def enter_final_review(session: Session) -> bool:
    reconcile_session(session)
    if not can_enter_final_review(session):
        return False
    for stage in STAGE_ORDER:
        if stage == "final_review":
            break
        mark_stage_complete(session, stage)
    session.flow_state["current_stage"] = "final_review"
    session.conversation_stage = ConversationStage.CONFIRMATION
    session.flow_state["final_review_shown"] = True
    session.flow_state.pop("current_step_id", None)
    set_current_question(session, None)
    sync_pending_fields(session)
    from backend.intelligence.qualification_builder import prepare_final_review_outbound
    prepare_final_review_outbound(session)
    return True


def mark_field_validated(session: Session, field: str, value: Any) -> bool:
    """Only persist field if value is valid (or optional empty)."""
    if field in OPTIONAL_FIELDS and (value is None or str(value).strip().lower() in INVALID_VALUES):
        session.mark_field_complete(field, "")
        return True
    if not is_valid_field_value(value, field=field):
        return False
    session.mark_field_complete(field, value)
    return True


_ENQUIRY_RESET_FIELDS = frozenset({
    "willing_to_create_project",
    "service_category",
    "assigned_consultant",
    "attachments",
    "has_attachments",
    "overview_property_type",
})


def _enquiry_fields_to_clear(session: Session) -> set[str]:
    fs = session.flow_state or {}
    dynamic = list(fs.get("service_questionnaire_required_fields") or [])
    service_fields = [
        f for f in session.extracted_fields
        if f.startswith("service_q") or f.startswith("order_") or f.startswith("file_order_")
    ]
    return set(_ENQUIRY_RESET_FIELDS) | set(dynamic) | set(service_fields)


def clear_service_questionnaire_answers(session: Session) -> None:
    """Remove answers for a prior service questionnaire before switching services."""
    fs = session.flow_state or {}
    reset_fields = set(fs.get("service_questionnaire_required_fields") or [])
    reset_fields.update(
        f for f in session.extracted_fields
        if f.startswith("service_q") or f.startswith("order_") or f.startswith("file_order_")
    )
    session.completed_fields = [f for f in session.completed_fields if f not in reset_fields]
    for field in reset_fields:
        session.extracted_fields.pop(field, None)


def clear_prior_enquiry_qualification(session: Session) -> None:
    """Remove a previous enquiry's service/qualification data for a fresh returning-user project."""
    from backend.integrations.tatva_service_questions import clear_questionnaire_cache

    reset_fields = _enquiry_fields_to_clear(session)
    session.completed_fields = [f for f in session.completed_fields if f not in reset_fields]
    for field in reset_fields:
        session.extracted_fields.pop(field, None)
    clear_service_questionnaire_answers(session)
    clear_questionnaire_cache(session)
    session.service_category = None
    session.active_consultant = None
    session.attachments = []
    session.summary_generated = False
    session.summary = None


def on_service_selected(session: Session, category: ServiceCategory) -> None:
    from backend.integrations.tatva_service_questions import clear_questionnaire_cache

    clear_service_questionnaire_answers(session)
    clear_questionnaire_cache(session)
    session.service_category = category
    session.active_consultant = None
    from backend.schemas.service import CONSULTANT_IDS
    session.active_consultant = CONSULTANT_IDS.get(category)
    session.flow_state["selected_service"] = category.value
    session.flow_state["assigned_consultant"] = session.active_consultant or ""
    mark_field_validated(session, "service_category", category.value)
    mark_field_validated(session, "assigned_consultant", session.active_consultant or "")
    mark_stage_complete(session, "ava_intro")
    mark_stage_complete(session, "client_details")
    mark_stage_complete(session, "service_selection")
    mark_stage_complete(session, "consultant_assignment")
    session.flow_state["current_stage"] = "service_questionnaire"
    session.flow_state.pop("current_step_id", None)
    session.flow_state.pop("last_stage_shown", None)
    session.conversation_stage = ConversationStage.DETAIL_COLLECTION
    reconcile_session(session)


def start_client_stage(session: Session) -> None:
    phone = session.phone_number or ""
    if phone.lower().startswith("whatsapp:"):
        phone = phone.split(":", 1)[-1]
    if phone and is_valid_field_value(phone.strip()):
        mark_field_validated(session, "phone_number", phone.strip())
    ensure_flow_state(session)
    mark_field_validated(session, "ava_intro_shown", True)
    mark_stage_complete(session, "ava_intro")
    session.flow_state["current_stage"] = "client_details"
    session.conversation_stage = ConversationStage.ROUTING
    reconcile_session(session)


def reset_for_edit_details(session: Session) -> None:
    ensure_flow_state(session)
    keep_fields = {
        "client_name", "phone_number", "city", "property_location",
        "willing_to_create_project",
        "email", "service_category",
    }
    session.completed_fields = [f for f in session.completed_fields if f in keep_fields and field_is_complete(session, f)]
    session.extracted_fields = {
        k: v for k, v in session.extracted_fields.items()
        if k in keep_fields and field_is_complete(session, k)
    }
    session.flow_state["completed_stages"] = [
        s for s in ("ava_intro", "client_details", "service_selection", "consultant_assignment") if is_stage_complete(session, s)
    ]
    session.flow_state["current_stage"] = "service_questionnaire"
    session.flow_state.pop("current_step_id", None)
    session.flow_state.pop("last_stage_shown", None)
    session.conversation_stage = ConversationStage.DETAIL_COLLECTION
    session.summary_generated = False
    session.summary = None
    reconcile_session(session)


def required_fields_for_summary(session: Session) -> list[str]:
    fields: list[str] = []
    for stage in STAGE_ORDER:
        if stage == "final_review":
            continue
        for f in required_fields_for_stage(session, stage):
            if f not in fields:
                fields.append(f)
    return fields


def is_qualification_complete(session: Session) -> bool:
    return can_enter_final_review(session)


def qualification_completion_pct(session: Session) -> int:
    required = required_fields_for_summary(session)
    if not required:
        return 0
    done = sum(1 for f in required if field_is_complete(session, f))
    return int((done / len(required)) * 100)


def needs_client_details(session: Session) -> bool:
    reconcile_session(session)
    if session.flow_state.get("project_declined"):
        return False
    return not is_stage_complete(session, "client_details")


def needs_service_selection(session: Session) -> bool:
    reconcile_session(session)
    if session.flow_state.get("project_declined"):
        return False
    return is_stage_complete(session, "client_details") and not is_stage_complete(session, "service_selection")


def is_collecting_qualification(session: Session) -> bool:
    if session.summary_generated:
        return False
    if session.flow_state.get("project_declined"):
        return False
    reconcile_session(session)
    if fs_current_stage(session) == "final_review":
        return False
    if needs_client_details(session) or needs_service_selection(session):
        return True
    return session.service_category is not None and not can_enter_final_review(session)


def missing_fields_report(session: Session) -> list[str]:
    missing: list[str] = []
    for stage in STAGE_ORDER:
        if stage == "final_review":
            break
        for f in required_fields_for_stage(session, stage):
            if not field_is_complete(session, f):
                missing.append(f)
    return missing

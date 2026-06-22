from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from backend.schemas.service import SERVICE_MENU


_COMMON_FIELD_LABELS: dict[str, dict[str, str]] = {
    "preferred_contact_time": {
        "morning": "Morning",
        "afternoon": "Afternoon",
        "evening": "Evening",
        "night": "Night",
    },
    "willing_to_create_project": {
        "yes": "Yes",
        "no": "No",
    },
}

_CONSULTANT_NAMES = {
    "aravind": "Aravind Narayanan",
    "aadhya": "Aadhya",
    "manjunath": "Manjunath Gowda",
    "vivek": "Vivek Shetty",
    "suresh": "Suresh Kumar",
    "kavya": "Kavya Nair",
    "riya": "Riya Mehta",
    "meera": "Meera Iyer",
    "vikram": "Vikram Desai",
    "anil": "Anil Reddy",
    "deepak": "Deepak Patil",
}

_SERVICE_LABELS = {cat.value: label for _n, cat, label, _c in SERVICE_MENU}
_FLOW_CACHE: dict[str, dict[str, dict[str, str]]] = {}


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


_VERBATIM_FIELDS = frozenset({
    "client_name",
    "city",
    "property_location",
    "phone_number",
    "email",
    "service_q4",
    "special_notes_extra",
    "req_functional_needs",
    "req_inspiration_notes",
})


def _is_user_entered_text(raw: str) -> bool:
    """True when the value looks like free-form user typing, not an internal MCQ slug."""
    if any(ch in raw for ch in (",", ";", ":", ".", "!", "?")):
        return True
    if " " in raw.strip():
        return True
    # Preserve mixed case (VidyMN, JP Nagar, iPhone, etc.)
    if raw != raw.lower() and raw != raw.upper():
        return True
    return False


def _prettify(value: Any) -> str:
    s = str(value or "").strip()
    if not s:
        return "—"
    s = s.replace("_", " ").replace("-", " ").strip()
    return " ".join(tok.capitalize() for tok in s.split())


def _service_flow_labels(service_category: str) -> dict[str, dict[str, str]]:
    if service_category in _FLOW_CACHE:
        return _FLOW_CACHE[service_category]

    path = _repo_root() / "backend" / "intelligence" / "flows" / f"{service_category}.json"
    if not path.exists():
        _FLOW_CACHE[service_category] = {}
        return {}

    data = json.loads(path.read_text(encoding="utf-8"))
    by_field: dict[str, dict[str, str]] = {}
    for step in data:
        field = str(step.get("field") or "")
        options = step.get("options", [])
        if not field or not isinstance(options, list):
            continue
        option_map: dict[str, str] = {}
        for opt in options:
            value = str(opt.get("value", "")).strip()
            label = str(opt.get("label", "")).strip()
            if value and label:
                option_map[value] = label
        if option_map:
            by_field[field] = option_map

    _FLOW_CACHE[service_category] = by_field
    return by_field


def _load_flow_steps(service_category: str) -> list[dict]:
    path = _repo_root() / "backend" / "intelligence" / "flows" / f"{service_category}.json"
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def prompt_to_client_label(prompt: str) -> str:
    """Short client-facing label derived from the qualification question."""
    text = (prompt or "").strip().rstrip("?").strip()
    low = text.lower()

    if "budget" in low:
        return "Budget range"
    if "monthly electricity bill" in low or "electricity bill" in low:
        return "Monthly electricity bill"
    if "control mode" in low:
        return "Control mode"
    if "automation systems" in low:
        return "Automation scope"
    if "style preference" in low:
        return "Style preference"
    if "paintable area" in low or "area to be painted" in low:
        return "Paintable area"
    if "finish type" in low or "type of finish" in low:
        return "Finish type"
    if "urgency" in low or "breakdown" in low:
        return "Urgency"
    if "approval" in low:
        return "Approvals status"
    if "interior project" in low or "interior type" in low:
        return "Interior scope"
    if "electrical work" in low:
        return "Electrical work type"
    if "property type" in low:
        return "Property type"
    if "installation" in low and "connectivity" in low:
        return "Installation type"
    if "use case" in low or "primary use" in low:
        return "Primary use case"
    if "painting" in low and "type" in low:
        return "Painting scope"
    if "project type" in low or "construction" in low:
        return "Project type"

    for prefix in (
        "which ", "what is your ", "what is the ", "what type of ",
        "what ", "is this an ", "is this a ", "is this ",
    ):
        if low.startswith(prefix):
            text = text[len(prefix) :].strip()
            low = text.lower()
            break

    for suffix in (
        " do you need",
        " are you interested in",
        " for interiors",
        " for automation",
        " for your project",
    ):
        if low.endswith(suffix):
            text = text[: -len(suffix)].strip()
            low = text.lower()

    if not text:
        return "Detail"
    return text[0].upper() + text[1:]


def _emoji_for_label(label: str) -> str:
    low = label.lower()
    if any(k in low for k in ("budget", "bill", "cost", "lakhs")):
        return "💰"
    if any(k in low for k in ("urgency", "timeline", "approval")):
        return "⏱️"
    if any(k in low for k in ("style", "finish", "design")):
        return "🎨"
    if any(k in low for k in ("control", "automation", "system")):
        return "🎛️"
    if any(k in low for k in ("property", "installation", "area")):
        return "🏡"
    if any(k in low for k in ("electrical", "solar", "energy")):
        return "⚡"
    if "paint" in low:
        return "🖌️"
    return "🏠"


def budget_field_for_service(service_category: str) -> str | None:
    """Field name that holds budget/bill info for this service (if any)."""
    for step in _load_flow_steps(service_category):
        field = str(step.get("field") or "")
        if not field.startswith("service_q"):
            continue
        prompt = (step.get("prompt") or "").lower()
        if "budget" in prompt or "electricity bill" in prompt or "monthly bill" in prompt:
            return field
    return None


def client_confirmation_highlights(
    service_category: str,
    snap: dict,
    *,
    max_notes_len: int = 140,
) -> list[tuple[str, str]]:
    """
    Service-aware (label, value) pairs for the client WhatsApp confirmation.
    Uses each flow's real Q1–Q3 prompts — never assumes Q3 is budget.
    """
    service_key = (service_category or "").strip()
    if not service_key:
        return []

    lines: list[tuple[str, str]] = []
    for step in _load_flow_steps(service_key):
        field = str(step.get("field") or "")
        if field not in ("service_q1", "service_q2", "service_q3"):
            continue
        raw = snap.get(field)
        if raw is None or str(raw).strip() in ("", "—", "none", "skipped"):
            continue
        label = prompt_to_client_label(str(step.get("prompt") or ""))
        emoji = _emoji_for_label(label)
        value = display_label(field, raw, service_category=service_key)
        lines.append((f"{emoji} {label}", value))

    notes = snap.get("service_q4")
    if notes and str(notes).strip().lower() not in ("", "—", "skip", "skipped", "none"):
        note_text = display_label("service_q4", notes, service_category=service_key)
        if len(note_text) > max_notes_len:
            note_text = note_text[: max_notes_len - 1] + "…"
        lines.append(("📝 Project notes", note_text))

    return lines


def display_label(field: str, value: Any, *, service_category: str = "") -> str:
    if value is None or value == "":
        return "—"
    if isinstance(value, list):
        return ", ".join(display_label(field, v, service_category=service_category) for v in value)

    raw = str(value).strip()
    if not raw:
        return "—"

    if field == "client_name":
        from backend.integrations.returning_user_flow import is_placeholder_client_name

        if is_placeholder_client_name(raw):
            return "—"

    if field in _VERBATIM_FIELDS:
        return raw

    if field == "service_category":
        return _SERVICE_LABELS.get(raw, _prettify(raw))
    if field in ("assigned_consultant", "consultant"):
        return _CONSULTANT_NAMES.get(raw.lower(), _prettify(raw))
    if field in _COMMON_FIELD_LABELS:
        mapped = _COMMON_FIELD_LABELS[field].get(raw.lower())
        if mapped:
            return mapped
        if _is_user_entered_text(raw):
            return raw
        return _prettify(raw)

    if service_category:
        field_map = _service_flow_labels(service_category).get(field, {})
        if raw in field_map:
            return field_map[raw]

    if _is_user_entered_text(raw):
        return raw

    return _prettify(raw)

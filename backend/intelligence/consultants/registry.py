"""
Consultant registry: maps service category to persona, enquiry config, openings.
"""
from __future__ import annotations
from typing import Callable, Optional

from backend.schemas.service import ServiceCategory, CONSULTANT_IDS, SERVICE_MENU
from backend.schemas.session import Session, ConversationStage
from backend.intelligence.consultants.enquiry_configs import ENQUIRY_CONFIG
from backend.intelligence import stage_engine as se
from backend.intelligence import hybrid_flow
from backend.intelligence.consultants.personas import get_base_identity, OPENING_MESSAGES

CHAT_TEMPLATE = """
{base_identity}

CURRENT CONVERSATION CONTEXT:
- Conversation Stage: {stage}
- Service: {service}
- Fields Collected: {completed_fields}
- Extracted So Far: {extracted_fields}
- Next Topics: {next_fields}

YOUR TASK FOR THIS TURN:
{task_instruction}

STYLE: Warm, consultative, exactly ONE question per response. 2-3 short sentences max.
Never quote exact prices or promise timelines. End with a question.
"""

VOICE_TEMPLATE = """
{base_identity}

Stage: {stage} | Service: {service}
Collected: {completed_fields}
Task: {task_instruction}

VOICE RULES: Max 2 sentences, one question, no markdown, no emojis.
"""


def get_consultant_id(category: ServiceCategory) -> str:
    return CONSULTANT_IDS[category]


def get_primary_parameters(category: ServiceCategory) -> list[str]:
    fields: list[str] = []
    for stage in se.STAGE_ORDER:
        if stage == "final_review":
            continue
        for f in se.STAGE_REQUIRED_FIELDS.get(stage, []):
            if f not in fields:
                fields.append(f)
    return fields


def get_secondary_parameters(category: ServiceCategory) -> list[str]:
    return list(ENQUIRY_CONFIG[category].get("secondary", []))


def get_field_hints(category: ServiceCategory) -> dict[str, str]:
    return dict(ENQUIRY_CONFIG[category].get("hints", {}))


def get_opening_message(consultant_id: str) -> str:
    return OPENING_MESSAGES.get(consultant_id, OPENING_MESSAGES["aadhya"])


def get_chat_prompt(
    consultant_id: str,
    service_label: str,
    stage: str,
    completed_fields: list,
    extracted_fields: dict,
    next_fields: list | None,
    task_instruction: str,
) -> str:
    return CHAT_TEMPLATE.format(
        base_identity=get_base_identity(consultant_id),
        stage=stage,
        service=service_label,
        completed_fields=", ".join(completed_fields) if completed_fields else "none",
        extracted_fields=str(extracted_fields) if extracted_fields else "none",
        next_fields=", ".join(next_fields) if next_fields else "confirm details",
        task_instruction=task_instruction,
    )


def get_voice_prompt(
    consultant_id: str,
    service_label: str,
    stage: str,
    completed_fields: list,
    extracted_fields: dict,
    next_fields: list | None,
    task_instruction: str,
) -> str:
    return VOICE_TEMPLATE.format(
        base_identity=get_base_identity(consultant_id),
        stage=stage,
        service=service_label,
        completed_fields=", ".join(completed_fields) if completed_fields else "none",
        extracted_fields=str(extracted_fields) if extracted_fields else "none",
        next_fields=", ".join(next_fields) if next_fields else "confirm",
        task_instruction=task_instruction,
    )


def get_service_label(category: ServiceCategory) -> str:
    for _num, cat, label, _name in SERVICE_MENU:
        if cat == category:
            return label
    return category.value


def get_next_fields(session: Session) -> list[str]:
    if not session.service_category:
        return ["client_name"]
    if hybrid_flow.has_active_flow(session):
        return []
    required = se.required_fields_for_summary(session)
    missing = [f for f in required if f not in session.completed_fields]
    return missing[:3] if missing else []


def is_enquiry_complete(session: Session) -> bool:
    if not session.service_category:
        return False
    if hybrid_flow.has_active_flow(session):
        return False
    return se.all_qualification_stages_complete(session)


def build_task_instruction(session: Session) -> str:
    if session.conversation_stage == ConversationStage.SUMMARY_GENERATED:
        return (
            "Thank the client warmly and confirm our team will follow up shortly."
        )
    if session.conversation_stage == ConversationStage.CONFIRMATION:
        collected = session.extracted_fields
        return (
            "Summarize the key project details collected and ask if everything is correct "
            "before we prepare their brief."
        )
    next_fields = get_next_fields(session)
    if not session.service_category:
        return "Ask which TatvaOps service they need help with."
    hints = get_field_hints(session.service_category)
    if not next_fields:
        return "Transition to confirmation: recap details and ask if they are correct."
    instruction = "Acknowledge the client naturally, then ask about ONE topic:\n"
    for nf in next_fields[:1]:
        hint = hints.get(nf, f"Ask about {nf}.")
        instruction += f"- {hint}\n"
    return instruction

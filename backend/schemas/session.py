"""
TatvaOps – Session Object Model (omnichannel)
"""
from __future__ import annotations
from typing import List, Optional, Dict, Any
from enum import Enum
from pydantic import BaseModel, Field
from datetime import datetime

from backend.schemas.service import ServiceCategory


class ConversationStage(str, Enum):
    ROUTING = "ROUTING"
    DISCOVERY = "DISCOVERY"
    DETAIL_COLLECTION = "DETAIL_COLLECTION"
    CONFIRMATION = "CONFIRMATION"
    SUMMARY_GENERATED = "SUMMARY_GENERATED"


class MessageRole(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class AttachmentMeta(BaseModel):
    file_name: str
    file_url: str
    mime_type: str = ""
    uploaded_at: datetime = Field(default_factory=datetime.utcnow)


class ConversationMessage(BaseModel):
    role: MessageRole
    content: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    extracted_fields: Dict[str, Any] = {}


class AIThinkingTrace(BaseModel):
    turn: int
    user_message: str
    detected_fields: Dict[str, Any] = {}
    next_field_target: Optional[str] = None
    stage_before: ConversationStage = ConversationStage.ROUTING
    stage_after: ConversationStage = ConversationStage.ROUTING
    guardrail_triggered: bool = False
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class Session(BaseModel):
    session_id: str
    phone_number: str
    channel: str = "whatsapp"
    active_consultant: Optional[str] = None  # nova | aravind | aadhya | ...
    service_category: Optional[ServiceCategory] = None
    conversation_history: List[ConversationMessage] = Field(default_factory=list)
    extracted_fields: Dict[str, Any] = Field(default_factory=dict)
    completed_fields: List[str] = Field(default_factory=list)
    conversation_stage: ConversationStage = ConversationStage.ROUTING
    thinking_traces: List[AIThinkingTrace] = Field(default_factory=list)
    summary_generated: bool = False
    summary: Optional[Dict[str, Any]] = None
    flow_state: Dict[str, Any] = Field(default_factory=dict)
    attachments: List[AttachmentMeta] = Field(default_factory=list)
    lead_score: Optional[int] = None
    lead_tier: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    last_active: datetime = Field(default_factory=datetime.utcnow)
    turn_count: int = 0

    def primary_parameters(self) -> List[str]:
        from backend.intelligence.stage_engine import required_fields_for_summary
        if self.service_category:
            return required_fields_for_summary(self)
        return [
            "client_name", "phone_number", "property_location",
            "preferred_contact_time", "willing_to_create_project", "overview_property_type",
        ]

    @property
    def field_completion_pct(self) -> int:
        from backend.intelligence.stage_engine import qualification_completion_pct
        if self.service_category or self.flow_state.get("current_stage"):
            return qualification_completion_pct(self)
        required = self.primary_parameters()
        if not required:
            return 0
        done = sum(1 for f in required if f in self.completed_fields)
        return int((done / len(required)) * 100)

    def add_message(self, role: MessageRole, content: str,
                    extracted: Dict[str, Any] | None = None) -> None:
        self.conversation_history.append(
            ConversationMessage(role=role, content=content,
                                extracted_fields=extracted or {})
        )
        self.last_active = datetime.utcnow()
        if role == MessageRole.USER:
            self.turn_count += 1

    def mark_field_complete(self, field_name: str, value: Any) -> None:
        self.extracted_fields[field_name] = value
        if field_name not in self.completed_fields:
            self.completed_fields.append(field_name)

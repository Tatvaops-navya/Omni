"""
Conversation controller — strict stage-based qualification, then final review.
"""
from __future__ import annotations

import re

from backend.schemas.session import Session, ConversationStage, MessageRole
from backend.intelligence.persona import GUARDRAIL_REDIRECT
from backend.intelligence import hybrid_flow
from backend.intelligence import stage_engine as se
from backend.intelligence.qualification_builder import format_final_review, get_final_review_outbound_step
from backend.intelligence import edit_flow
from backend.intelligence.lead_scorer import apply_lead_score
from backend.intelligence.nova_router import (
    detect_service_from_step,
    is_service_more_selection,
    get_consultant_display_name,
    get_service_selection_outbound_step,
)
from backend.intelligence.consultants.registry import get_service_label
from backend.schemas.service import CONSULTANT_IDS
from backend.summarizer.summary_generator import get_summary_generator
from backend.integrations.tatva_users import register_tatva_user_for_session
from backend.integrations.tatva_service_questions import ensure_questionnaire_loaded
from backend.integrations.tatva_enquiry_submit import submit_service_questionnaire
from backend.utils.logger import log_event
from backend.utils.session_idle import is_greeting_message, had_conversation_progress

OFF_TOPIC_KEYWORDS = [
    "stock", "crypto", "bitcoin", "recipe", "weather", "cricket", "movie",
    "exam", "job", "salary", "politics", "news", "visa", "marriage",
]


class AgentResponse:
    def __init__(
        self,
        text: str,
        session: Session,
        summary_generated: bool = False,
        follow_up_text: str | None = None,
    ):
        self.text = text
        self.session = session
        self.summary_generated = summary_generated
        self.follow_up_text = follow_up_text


def _is_off_topic(message: str) -> bool:
    """Whole-word match only — avoids false positives like *livestock* → *stock*."""
    lower = message.lower()
    return any(re.search(rf"\b{re.escape(kw)}\b", lower) for kw in OFF_TOPIC_KEYWORDS)


def _should_skip_off_topic_guardrail(session: Session) -> bool:
    """Structured qualification answers must never get the generic interior-design redirect."""
    if se.is_collecting_qualification(session):
        return True
    if edit_flow.is_active(session):
        return True
    return False


def _should_send_eva_intro_for_greeting(session: Session, user_message: str) -> bool:
    """Greetings start (or restart) with the full EVA welcome — never treat as an answer."""
    if not is_greeting_message(user_message):
        return False
    if session.summary_generated or session.flow_state.get("project_declined"):
        return False
    return True


def _reset_session_to_eva_start(session: Session) -> None:
    """Clear in-progress qualification so the user can restart from EVA welcome."""
    phone = (session.phone_number or "").strip()
    if phone.lower().startswith("whatsapp:"):
        phone = phone.split(":", 1)[-1]
    session.conversation_history = []
    session.extracted_fields = {}
    session.completed_fields = []
    session.attachments = []
    session.service_category = None
    session.active_consultant = None
    session.conversation_stage = ConversationStage.ROUTING
    session.summary_generated = False
    session.summary = None
    session.flow_state = {}
    edit_flow.clear_edit_mode(session)
    hybrid_flow.init_flow(session)
    se.start_client_stage(session)
    if phone:
        se.mark_field_validated(session, "phone_number", phone)


def _end_conversation(session: Session) -> None:
    """Mark session complete and clear active qualification/edit state."""
    edit_flow.clear_edit_mode(session)
    session.flow_state["conversation_ended"] = True
    session.flow_state.pop("current_step_id", None)
    session.flow_state.pop("current_question", None)
    session.flow_state.pop("pending_fields", None)
    session.flow_state.pop("final_review_outbound_step", None)
    session.flow_state.pop("final_review_shown", None)


class ConversationController:

    def __init__(self):
        self.summarizer = get_summary_generator()

    async def _run_hybrid(
        self,
        session: Session,
        user_message: str,
        *,
        button_text: str | None = None,
        button_payload: str | None = None,
        list_id: str | None = None,
    ) -> AgentResponse | None:
        hybrid_flow.init_flow(session)

        if se.can_enter_final_review(session) and not hybrid_flow.has_active_flow(session):
            if se.enter_final_review(session):
                recap = format_final_review(session)
                session.add_message(MessageRole.ASSISTANT, recap)
                return AgentResponse(text=recap, session=session)

        if not hybrid_flow.has_active_flow(session):
            return None

        hybrid_reply, handled = hybrid_flow.process_hybrid_turn(
            session, user_message,
            button_text=button_text, button_payload=button_payload, list_id=list_id,
        )
        if handled and session.flow_state.pop("register_tatva_user", False):
            await register_tatva_user_for_session(session)
        if handled and hybrid_reply:
            session.add_message(MessageRole.ASSISTANT, hybrid_reply)
            return AgentResponse(text=hybrid_reply, session=session)
        return None

    async def process_message(
        self,
        session: Session,
        user_message: str,
        channel: str = "whatsapp",
        button_text: str | None = None,
        button_payload: str | None = None,
        list_id: str | None = None,
    ) -> AgentResponse:
        se.reconcile_session(session)
        await log_event("USER_MESSAGE", session_id=session.session_id,
                        data={
                            "message": user_message,
                            "stage": session.conversation_stage,
                            "flow_stage": se.fs_current_stage(session),
                            "pending_fields": session.flow_state.get("pending_fields", []),
                            "current_question": session.flow_state.get("current_question"),
                        })

        if session.summary_generated or session.conversation_stage == ConversationStage.SUMMARY_GENERATED:
            lower = user_message.lower().strip()
            if lower.startswith(("thank", "thx", "ty ", "ty")) or lower in ("ty", "thanks", "thank you", "thankyou"):
                thanks = (
                    "You're welcome! 😊\n\n"
                    "Your enquiry is already with our team — we'll contact you during your preferred time.\n\n"
                    "Thank you for choosing TatvaOps."
                )
            else:
                thanks = (
                    "Your enquiry has already been submitted. "
                    "Our team will contact you during your preferred time.\n\n"
                    "Thank you for choosing TatvaOps."
                )
            session.add_message(MessageRole.USER, user_message)
            session.add_message(MessageRole.ASSISTANT, thanks)
            return AgentResponse(text=thanks, session=session)

        if session.flow_state.get("project_declined"):
            session.add_message(MessageRole.USER, user_message)
            hold = (
                "Thank you for connecting with TatvaOps. "
                "If you would like to start a new enquiry, please restart after 5 minutes."
            )
            session.add_message(MessageRole.ASSISTANT, hold)
            return AgentResponse(text=hold, session=session)

        if (
            _should_send_eva_intro_for_greeting(session, user_message)
            and had_conversation_progress(session)
        ):
            session.add_message(MessageRole.USER, user_message)
            _reset_session_to_eva_start(session)
            intro = hybrid_flow.first_client_message()
            session.add_message(MessageRole.ASSISTANT, intro)
            session.flow_state["last_stage_shown"] = "client_details"
            return AgentResponse(text=intro, session=session)

        in_review = (
            se.is_in_final_review(session)
            or (
                se.can_enter_final_review(session)
                and (
                    session.flow_state.get("final_review_shown")
                    or session.conversation_stage == ConversationStage.CONFIRMATION
                )
            )
        )
        if in_review:
            session.add_message(MessageRole.USER, user_message)

            if edit_flow.wants_confirm_submit(
                user_message,
                list_id=list_id or "",
                button_payload=button_payload or "",
                button_text=button_text or "",
            ):
                if not se.can_enter_final_review(session):
                    se.reconcile_session(session)
                    step = hybrid_flow.get_current_step(session)
                    msg = hybrid_flow.format_step_message(step) if step else "Please complete the remaining questions first."
                    session.add_message(MessageRole.ASSISTANT, msg)
                    return AgentResponse(text=msg, session=session)

                summary = await self.summarizer.generate(session)
                session.summary = summary.model_dump()
                session.summary_generated = True
                session.conversation_stage = ConversationStage.SUMMARY_GENERATED
                apply_lead_score(session)
                _end_conversation(session)
                await submit_service_questionnaire(session)
                tatva_summary = session.flow_state.get("tatva_enquiry_summary")
                confirmation_text = summary.client_confirmation_text(
                    tatva_enquiry_summary=tatva_summary if isinstance(tatva_summary, dict) else None,
                )
                address_cta_text = summary.client_platform_address_cta_text()
                session.add_message(MessageRole.ASSISTANT, confirmation_text)
                session.add_message(MessageRole.ASSISTANT, address_cta_text)
                await log_event("SUMMARY_GENERATED", session_id=session.session_id,
                                data={"lead_score": session.lead_score, "channel": channel})
                return AgentResponse(
                    text=confirmation_text,
                    session=session,
                    summary_generated=True,
                    follow_up_text=address_cta_text,
                )

            review_step = get_final_review_outbound_step(session)
            hold = hybrid_flow.invalid_choice_reply(review_step)
            session.add_message(MessageRole.ASSISTANT, hold)
            return AgentResponse(text=hold, session=session)

        if session.conversation_stage == ConversationStage.CONFIRMATION and not se.can_enter_final_review(session):
            session.conversation_stage = ConversationStage.DETAIL_COLLECTION
            se.reconcile_session(session)

        session.add_message(MessageRole.USER, user_message)

        if _is_off_topic(user_message) and not _should_skip_off_topic_guardrail(session):
            session.add_message(MessageRole.ASSISTANT, GUARDRAIL_REDIRECT)
            return AgentResponse(text=GUARDRAIL_REDIRECT, session=session)

        if se.needs_client_details(session) and not session.flow_state.get("final_review_shown"):
            se.start_client_stage(session)
            if _should_send_eva_intro_for_greeting(session, user_message):
                intro = hybrid_flow.first_client_message()
                session.add_message(MessageRole.ASSISTANT, intro)
                session.flow_state["last_stage_shown"] = "client_details"
                return AgentResponse(text=intro, session=session)
            resp = await self._run_hybrid(session, user_message,
                                        button_text=button_text, button_payload=button_payload, list_id=list_id)
            if resp:
                return resp
            session.flow_state["last_stage_shown"] = "client_details"
            return AgentResponse(text=hybrid_flow.first_client_message(), session=session)

        if se.needs_service_selection(session) and not session.flow_state.get("final_review_shown"):
            # Prefer interactive payload signals when present (WhatsApp list/button taps)
            selection_input = (list_id or button_payload or button_text or user_message or "").strip()

            if is_service_more_selection(
                list_id=list_id or "",
                button_payload=button_payload or "",
                button_text=button_text or "",
                user_message=user_message or "",
            ):
                session.flow_state["service_list_page"] = 2
                msg = "Choose Other Services"
                session.add_message(MessageRole.ASSISTANT, msg)
                return AgentResponse(text=msg, session=session)

            step = get_service_selection_outbound_step(session)
            category = detect_service_from_step(selection_input, step)
            if category is None:
                msg = hybrid_flow.invalid_choice_reply(step)
                session.add_message(MessageRole.ASSISTANT, msg)
                return AgentResponse(text=msg, session=session)

            session.flow_state.pop("service_list_page", None)
            consultant_id = CONSULTANT_IDS[category]
            consultant_name = get_consultant_display_name(category)
            service_label = get_service_label(category)
            session.active_consultant = consultant_id
            se.on_service_selected(session, category)
            await ensure_questionnaire_loaded(session)
            se.reconcile_session(session)

            client_name = (session.extracted_fields.get("client_name") or "").strip()
            greet = f"Perfect, {client_name} ✨" if client_name else "Perfect ✨"
            first_name = consultant_name.split()[0] if consultant_name else "our consultant"
            handoff = (
                f"{greet}\n"
                f"I'm connecting you with {consultant_name}, our {service_label} specialist.\n\n"
                f"{first_name} will now guide you through a few quick questions "
                "to understand your requirements better."
            )
            handoff = hybrid_flow.append_first_step_to_handoff(session, handoff)
            session.add_message(MessageRole.ASSISTANT, handoff)
            await log_event("SERVICE_SELECTED", session_id=session.session_id,
                            data={"consultant": consultant_id, "service": str(category)})
            return AgentResponse(text=handoff, session=session)

        if se.is_collecting_qualification(session):
            session.conversation_stage = ConversationStage.DETAIL_COLLECTION
            if session.service_category:
                await ensure_questionnaire_loaded(session)
                se.reconcile_session(session)
            resp = await self._run_hybrid(session, user_message,
                                        button_text=button_text, button_payload=button_payload, list_id=list_id)
            if resp:
                return resp
            step = hybrid_flow.get_current_step(session)
            if step:
                msg = hybrid_flow.format_step_message(step)
                session.add_message(MessageRole.ASSISTANT, msg)
                return AgentResponse(text=msg, session=session)

        if se.can_enter_final_review(session):
            se.enter_final_review(session)
            recap = format_final_review(session)
            session.add_message(MessageRole.ASSISTANT, recap)
            return AgentResponse(text=recap, session=session)

        fallback = "Please answer the current question, or reply *RESTART45* to start over."
        session.add_message(MessageRole.ASSISTANT, fallback)
        return AgentResponse(text=fallback, session=session)


_controller: ConversationController | None = None


def get_controller() -> ConversationController:
    global _controller
    if _controller is None:
        _controller = ConversationController()
    return _controller

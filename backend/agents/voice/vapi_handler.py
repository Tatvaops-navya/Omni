"""
Aadhya – Vapi Voice Webhook Handler
Processes Vapi call events and routes through the ConversationController.
"""
from __future__ import annotations
from datetime import datetime
from typing import Any
from fastapi import APIRouter, Request, HTTPException

from backend.schemas.session import Session, ConversationStage, MessageRole
from backend.intelligence.conversation_controller import get_controller
from backend.intelligence.consultants.registry import get_opening_message
from backend.intelligence import stage_engine as se
from backend.storage.redis_store import get_session, save_session
from backend.storage import supabase_store
from backend.agents.voice.voice_response_optimizer import optimize_for_voice
from backend.utils.logger import log_event
from backend.utils.session_idle import (
    is_session_idle_expired,
    is_greeting_message,
    had_conversation_progress,
    build_idle_fresh_start_reply,
    start_fresh_session,
)

router = APIRouter()


@router.post("/webhook/vapi")
async def vapi_webhook(request: Request):
    """
    Vapi sends JSON POST with a 'message' object.
    We handle transcript events and return assistant.say responses.
    """
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    message = body.get("message", {})
    msg_type = message.get("type", "")

    # ─── Handle call start ────────────────────────────────────────────────
    if msg_type == "assistant-request":
        # Vapi is asking for assistant config — return our ElevenLabs voice config
        return _assistant_config_response(
            "Hello, welcome to TatvaOps. I'm EVA. "
            "Which service do you need? Construction, interiors, painting, electrical, solar, or home automation?"
        )

    # ─── Handle transcripts ───────────────────────────────────────────────
    if msg_type == "transcript":
        # We no longer process AI logic here, because Vapi Custom LLM
        # sends requests directly to the /chat/completions endpoint.
        # This event is just for monitoring if needed.
        return {"results": []}

    # ─── Handle end-of-call ───────────────────────────────────────────────
    if msg_type == "end-of-call-report":
        call = body.get("call", {})
        call_id = call.get("id", "unknown")
        session_id = f"voice_{call_id}"
        await log_event("CALL_ENDED", session_id=session_id,
                        data={"event": "call_ended", "call_id": call_id})
        return {"status": "ok"}

    return {"results": []}


def _say_response(text: str) -> dict:
    """Vapi response format to make the assistant speak."""
    return {
        "results": [{
            "toolCallId": "aadhya_response",
            "result": text,
        }]
    }


@router.post("/webhook/vapi/chat/completions")
async def vapi_chat_completions(request: Request):
    """
    Vapi Custom LLM endpoint.
    Vapi calls this to get the next assistant message.
    It expects an OpenAI-compatible /chat/completions response.
    Supports both streaming (SSE) and non-streaming responses.
    """
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    is_streaming = body.get("stream", False)

    # Find the latest user message
    messages = body.get("messages", [])
    if not messages:
        return _build_response(
            "Welcome to TatvaOps. Which service do you need? Say a number from 1 to 11.",
            is_streaming,
        )

    last_user_msg = None
    for msg in reversed(messages):
        if msg.get("role") == "user":
            content = msg.get("content", "")
            # content can be a string or a list of content parts
            if isinstance(content, list):
                last_user_msg = " ".join(
                    part.get("text", "") for part in content if isinstance(part, dict)
                ).strip()
            else:
                last_user_msg = content.strip()
            break

    if not last_user_msg:
        return _build_response(
            "Welcome to TatvaOps. Which service do you need? Say a number from 1 to 11.",
            is_streaming,
        )

    # Build session ID from call data
    call = body.get("call", {})
    call_id = call.get("id", "unknown_call")
    phone = call.get("customer", {}).get("number", call_id)
    session_id = f"voice_{call_id}"

    # Load or create session
    session = await get_session(session_id)
    if session and is_session_idle_expired(session):
        stale_session = session
        await start_fresh_session(session_id, phone, channel="voice", reason="idle_timeout")
        session = await get_session(session_id)
        reply = build_idle_fresh_start_reply(stale_session, last_user_msg)
        se.start_client_stage(session)
        session.add_message(MessageRole.ASSISTANT, reply)
        await save_session(session)
        await supabase_store.upsert_session_log(session)
        return _build_response(optimize_for_voice(reply), is_streaming)

    if (
        session
        and last_user_msg
        and not session.summary_generated
        and not session.flow_state.get("project_declined")
        and is_greeting_message(last_user_msg)
        and had_conversation_progress(session)
    ):
        await start_fresh_session(session_id, phone, channel="voice", reason="greeting_restart")
        session = await get_session(session_id)

    if session is None:
        session = Session(
            session_id=session_id,
            phone_number=phone,
            channel="voice",
            conversation_stage=ConversationStage.ROUTING,
            created_at=datetime.utcnow(),
            last_active=datetime.utcnow(),
        )
        await log_event("SESSION_START", session_id=session_id,
                        data={"phone": phone, "channel": "voice"})

    # Route through controller
    controller = get_controller()
    try:
        agent_response = await controller.process_message(
            session=session,
            user_message=last_user_msg,
            channel="voice",
        )
    except Exception as e:
        await log_event("API_ERROR", session_id=session_id,
                        data={"error": str(e), "phase": "vapi_custom_llm"})
        fallback = "Could you give me just a moment, I'm pulling up your details."
        await save_session(session)
        return _build_response(fallback, is_streaming)

    # Optimize for voice (append follow-up CTA in one spoken turn when present)
    combined_text = agent_response.text or ""
    if agent_response.follow_up_text:
        combined_text = f"{combined_text}\n\n{agent_response.follow_up_text}"
    voice_text = optimize_for_voice(combined_text)

    # Persist
    await save_session(agent_response.session)
    await supabase_store.upsert_session_log(agent_response.session)

    if agent_response.session.flow_state.get("project_declined"):
        await supabase_store.persist_terminal_enquiry(agent_response.session)

    if agent_response.summary_generated and agent_response.session.summary:
        await supabase_store.persist_terminal_enquiry(agent_response.session)
        try:
            from backend.schemas.summary import ProjectSummary
            summary_obj = ProjectSummary.model_validate(agent_response.session.summary)
            await supabase_store.save_summary(summary_obj, phone_number=phone)
        except Exception:
            pass

    return _build_response(voice_text, is_streaming)


def _build_response(text: str, stream: bool = False):
    """Return either an SSE stream or a plain JSON response."""
    if stream:
        return _openai_stream_response(text)
    return _openai_response(text)


def _openai_response(text: str) -> dict:
    """Format the response exactly how Vapi Custom LLM expects it (non-streaming)."""
    return {
        "id": f"chatcmpl-aadhya-{int(datetime.utcnow().timestamp())}",
        "object": "chat.completion",
        "created": int(datetime.utcnow().timestamp()),
        "model": "aadhya-backend",
        "choices": [{
            "index": 0,
            "message": {
                "role": "assistant",
                "content": text
            },
            "finish_reason": "stop"
        }]
    }


def _openai_stream_response(text: str):
    """Return an SSE streaming response compatible with OpenAI chat completions."""
    import json
    from fastapi.responses import StreamingResponse

    chunk_id = f"chatcmpl-aadhya-{int(datetime.utcnow().timestamp())}"
    created = int(datetime.utcnow().timestamp())

    def generate():
        # First chunk: role
        chunk1 = {
            "id": chunk_id,
            "object": "chat.completion.chunk",
            "created": created,
            "model": "aadhya-backend",
            "choices": [{
                "index": 0,
                "delta": {"role": "assistant", "content": ""},
                "finish_reason": None
            }]
        }
        yield f"data: {json.dumps(chunk1)}\n\n"

        # Second chunk: full content
        chunk2 = {
            "id": chunk_id,
            "object": "chat.completion.chunk",
            "created": created,
            "model": "aadhya-backend",
            "choices": [{
                "index": 0,
                "delta": {"content": text},
                "finish_reason": None
            }]
        }
        yield f"data: {json.dumps(chunk2)}\n\n"

        # Final chunk: stop
        chunk3 = {
            "id": chunk_id,
            "object": "chat.completion.chunk",
            "created": created,
            "model": "aadhya-backend",
            "choices": [{
                "index": 0,
                "delta": {},
                "finish_reason": "stop"
            }]
        }
        yield f"data: {json.dumps(chunk3)}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
    )


def _assistant_config_response(opening_message: str) -> dict:
    """
    Returns Vapi assistant configuration.
    This is sent when Vapi first establishes a call.
    """
    from backend.config import get_settings
    s = get_settings()
    return {
        "assistant": {
            "firstMessage": opening_message,
            "voice": {
                "provider": "11labs",
                "voiceId": s.elevenlabs_voice_id or "EXAVITQu4vr4xnSDxMaL",  # Default: Bella
                "stability": 0.6,
                "similarityBoost": 0.85,
            },
            "transcriber": {
                "provider": "deepgram",
                "model": "nova-2",
                "language": "en-IN",
            },
            "model": {
                "provider": "custom-llm",
                "url": f"{s.base_url.rstrip('/')}/webhook/vapi/chat/completions",
            },
            "endCallMessage": "Thank you for speaking with me. Our team will be in touch with your design brief soon. Have a wonderful day!",
            "endCallPhrases": ["goodbye", "bye", "that's all", "thank you bye", "ok thanks bye"],
        }
    }

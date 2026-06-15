"""
TatvaOps – Twilio WhatsApp Sender
Supports plain text and MCQ-style messages.
Interactive tap options require Twilio Content templates; falls back to formatted text.
"""
from __future__ import annotations
from typing import Any, Optional
import json

from backend.config import get_settings

settings = get_settings()
_twilio_client = None

# Twilio WhatsApp body limit is 1600 chars (error 21617)
WHATSAPP_MAX_CHARS = 1500


def chunk_whatsapp_body(body: str, max_len: int = WHATSAPP_MAX_CHARS) -> list[str]:
    """Split long text into WhatsApp-safe chunks."""
    text = (body or "").strip()
    if not text:
        return [""]
    if len(text) <= max_len:
        return [text]

    chunks: list[str] = []
    parts = text.split("\n\n")
    current = ""
    for part in parts:
        candidate = f"{current}\n\n{part}".strip() if current else part
        if len(candidate) <= max_len:
            current = candidate
            continue
        if current:
            chunks.append(current)
            current = ""
        while len(part) > max_len:
            chunks.append(part[:max_len])
            part = part[max_len:]
        current = part
    if current:
        chunks.append(current)
    return chunks or [text[:max_len]]


def _get_client():
    global _twilio_client
    if _twilio_client is None:
        try:
            from twilio.rest import Client
            _twilio_client = Client(settings.twilio_account_sid, settings.twilio_auth_token)
        except Exception as e:
            print(f"[Twilio] Client init error: {e}")
    return _twilio_client


async def send_whatsapp_message(to: str, body: str) -> bool:
    """Send a plain WhatsApp message (auto-splits if over Twilio limit)."""
    chunks = chunk_whatsapp_body(body)
    if len(chunks) == 1:
        return await send_whatsapp_flow(to, chunks[0], step=None)
    ok = True
    total = len(chunks)
    for i, chunk in enumerate(chunks):
        prefix = f"📄 Part {i + 1}/{total}\n\n" if total > 1 else ""
        sent = await send_whatsapp_flow(to, prefix + chunk, step=None)
        ok = ok and sent
    return ok


async def send_context_then_mcq_list(
    to: str,
    context_body: str,
    step: Optional[dict[str, Any]],
) -> bool:
    """
    Send a long text block first, then a separate WhatsApp list-picker.
    Avoids appending numbered fallbacks to a multi-paragraph summary.
    """
    enriched = enrich_whatsapp_mcq_step(step) if step else None
    if (
        enriched
        and enriched.get("type") == "mcq"
        and mcq_uses_interactive_delivery(enriched)
    ):
        import asyncio

        list_prompt = str(
            enriched.get("twilio_list_prompt") or enriched.get("prompt") or "Choose option"
        ).strip()
        if (context_body or "").strip():
            await send_whatsapp_message(to, context_body.strip())
            await asyncio.sleep(1.0)
        return await send_whatsapp_flow(to, list_prompt, step=enriched)
    if enriched and enriched.get("type") == "mcq":
        prompt_only = str(enriched.get("prompt") or "Please choose one option.").strip()
        ok = True
        if (context_body or "").strip():
            ok = await send_whatsapp_message(to, context_body.strip())
        fallback = _format_mcq_plain_fallback(prompt_only, enriched)
        sent = await _send_plain(to, fallback)
        return ok and sent
    return await send_whatsapp_flow(to, context_body, step=enriched)


async def send_whatsapp_flow(to: str, body: str, step: Optional[dict[str, Any]] = None) -> bool:
    """
    Send flow message. For MCQ steps, tries Twilio interactive options when
    TWILIO_WHATSAPP_QUICK_REPLY=true and Content SID is configured.
    Otherwise sends formatted text (user replies with number or option name).
    """
    if (
        step
        and step.get("type") == "mcq"
        and getattr(settings, "twilio_whatsapp_quick_reply", False)
        and _should_send_interactive(step)
    ):
        options = step.get("options", [])
        quick_opts = [o for o in options if not _is_other_option(o)]
        opt_cap = int(step.get("twilio_option_count") or step.get("twilio_list_slots") or 0)
        if opt_cap:
            quick_opts = quick_opts[:opt_cap]
        min_opts = 1 if str(step.get("field", "")) == "__final_review__" else 2
        if min_opts <= len(quick_opts) <= 10:
            sent = await _send_interactive_options(to, body, quick_opts, step=step)
            if sent:
                return True
            print(
                "[Twilio] Interactive list failed — sending numbered plain-text options. "
                "Check TWILIO_WHATSAPP_QUICK_REPLY, Content SIDs, and Render logs."
            )
            body = _format_mcq_plain_fallback(body, step)
    return await _send_plain(to, body)


def _format_mcq_plain_fallback(body: str, step: dict[str, Any]) -> str:
    """Numbered options when WhatsApp list-picker cannot be sent."""
    options = [o for o in (step.get("options") or []) if not _is_other_option(o)]
    if not options:
        return body
    header = (body or "").strip() or str(step.get("prompt") or "Please choose one option.").strip()
    lines = [header, ""]
    for i, opt in enumerate(options, 1):
        lines.append(f"{i}. {opt.get('label', '')}")
    if any(_is_other_option(o) for o in step.get("options") or []):
        lines.extend(["", "Or type *Other* and describe your requirement."])
    return "\n".join(lines)


def _resolve_content_sid(step: dict[str, Any]) -> str:
    sid = str(step.get("twilio_content_sid") or "").strip()
    if sid:
        return sid
    field = str(step.get("field", ""))
    if field == "service_category":
        return str(getattr(settings, "twilio_service_selection_content_sid", "") or "").strip()
    if step.get("use_dynamic_list"):
        return (
            str(getattr(settings, "twilio_service_selection_content_sid", "") or "").strip()
            or str(getattr(settings, "twilio_whatsapp_interactive_content_sid", "") or "").strip()
        )
    return ""


def mcq_uses_interactive_delivery(step: Optional[dict[str, Any]]) -> bool:
    """True when we will send a Twilio list-picker (not plain numbered text)."""
    if not step or step.get("type") != "mcq":
        return False
    if not getattr(settings, "twilio_whatsapp_quick_reply", False):
        return False
    return _should_send_interactive(step)


def _variable_mcq_list_sid(option_count: int) -> str:
    fallback = str(getattr(settings, "twilio_whatsapp_interactive_content_sid", "") or "").strip()
    if option_count == 5:
        return (
            str(getattr(settings, "twilio_mcq_list_5_content_sid", "") or "").strip()
            or fallback
        )
    if option_count == 1:
        return str(getattr(settings, "twilio_mcq_list_1_content_sid", "") or "").strip()
    if option_count == 2:
        return str(getattr(settings, "twilio_mcq_list_2_content_sid", "") or "").strip()
    if option_count in (3, 4):
        return (
            str(getattr(settings, "twilio_mcq_list_4_content_sid", "") or "").strip()
            or fallback
        )
    return ""


def _should_send_interactive(step: dict[str, Any]) -> bool:
    if step.get("force_plain_mcq"):
        return False
    field = str(step.get("field", ""))
    if step.get("twilio_content_sid") or step.get("use_dynamic_list"):
        return bool(_resolve_content_sid(step))
    if field == "service_category":
        return bool(getattr(settings, "twilio_service_selection_content_sid", ""))
    if field in ("willing_to_create_project",) or field.startswith("__edit_") or field == "__final_review__":
        return bool(_variable_mcq_list_sid(len([o for o in (step.get("options") or []) if not _is_other_option(o)])))
    return False


def enrich_whatsapp_mcq_step(step: Optional[dict[str, Any]]) -> Optional[dict[str, Any]]:
    """
    Enable WhatsApp list-picker for MCQ steps that only have plain JSON options
    (e.g. irrigation, plumbing) using the shared dynamic list template.
    """
    if not step or step.get("type") != "mcq":
        return step
    if not getattr(settings, "twilio_whatsapp_quick_reply", False):
        return step

    options = step.get("options") or []
    quick_opts = [o for o in options if not _is_other_option(o)]
    field = str(step.get("field", ""))
    if len(quick_opts) < 2 and field != "__final_review__":
        return step

    from backend.schemas.service import WHATSAPP_SERVICE_LIST_ROWS

    max_slots = min(len(quick_opts), WHATSAPP_SERVICE_LIST_ROWS, 10)
    out = dict(step)
    # Option count for labels sent; template row count set below when using dynamic list.
    out["twilio_option_count"] = max_slots
    prompt = str(step.get("prompt") or "Please choose one option.").strip()
    if not out.get("twilio_list_prompt"):
        out["twilio_list_prompt"] = _twilio_list_prompt({"prompt": prompt})

    enriched_options: list[dict[str, Any]] = []
    for opt in quick_opts[:max_slots]:
        label = str(opt.get("label") or "")
        enriched_options.append({
            **opt,
            "whatsapp_label": label,
        })
    out["options"] = enriched_options
    long_labels = any(len(str(o.get("label") or "")) > WHATSAPP_LIST_TITLE_MAX for o in quick_opts)

    if out.get("twilio_content_sid"):
        field = str(out.get("field", ""))
        if (
            out.get("require_content_variables")
            or field.startswith("service_q")
            or field.startswith("__edit_")
            or field == "__final_review__"
            or field == "preferred_contact_time"
            or field == "willing_to_create_project"
        ):
            out["require_content_variables"] = True
        if _template_supports_row_descriptions(out):
            out["twilio_list_use_descriptions"] = True
        elif long_labels:
            out["force_plain_mcq"] = True
        return out

    variable_sid = _variable_mcq_list_sid(len(quick_opts))
    min_opts = 1 if field == "__final_review__" else 2
    if variable_sid and min_opts <= len(quick_opts) <= 5:
        out["twilio_content_sid"] = variable_sid
        out["require_content_variables"] = True
        out["twilio_list_slots"] = len(quick_opts)
        out["twilio_list_use_descriptions"] = True
        return out

    dynamic_sid = (
        str(getattr(settings, "twilio_service_selection_content_sid", "") or "").strip()
        or str(getattr(settings, "twilio_whatsapp_interactive_content_sid", "") or "").strip()
    )
    # Shared template is fixed at WHATSAPP_SERVICE_LIST_ROWS rows — only use it when
    # every row has a real option; otherwise WhatsApp shows {{option_N_label}} placeholders.
    if len(quick_opts) != WHATSAPP_SERVICE_LIST_ROWS:
        return out

    out["use_dynamic_list"] = True
    out["require_content_variables"] = True
    out["twilio_content_sid"] = dynamic_sid
    out["twilio_list_slots"] = WHATSAPP_SERVICE_LIST_ROWS
    out["twilio_list_use_descriptions"] = True
    return out


def _is_other_option(opt: dict) -> bool:
    val = str(opt.get("value", "")).lower()
    label = str(opt.get("label", "")).lower()
    return val == "__other__" or label == "other" or label.startswith("other ")


async def _send_plain(to: str, body: str) -> bool:
    client = _get_client()
    if not client:
        print(f"[Twilio] Not configured — would send to {to}: {body[:80]}")
        return False
    try:
        from backend.utils.retry import with_retry
        await with_retry(_send_once, client=client, to=to, body=body, session_id=to)
        return True
    except Exception as e:
        print(f"[Twilio] Send error: {e}")
        return False


WHATSAPP_LIST_TITLE_MAX = 24
WHATSAPP_LIST_DESCRIPTION_MAX = 72
# Back-compat alias
WHATSAPP_LIST_LABEL_MAX = WHATSAPP_LIST_TITLE_MAX


def _variable_mcq_content_sids() -> set[str]:
    sids = {
        str(getattr(settings, "twilio_mcq_list_5_content_sid", "") or "").strip(),
        str(getattr(settings, "twilio_mcq_list_4_content_sid", "") or "").strip(),
        str(getattr(settings, "twilio_mcq_list_2_content_sid", "") or "").strip(),
        str(getattr(settings, "twilio_mcq_list_1_content_sid", "") or "").strip(),
        str(getattr(settings, "twilio_whatsapp_interactive_content_sid", "") or "").strip(),
        str(getattr(settings, "twilio_service_selection_content_sid", "") or "").strip(),
    }
    return {s for s in sids if s}


def _template_supports_row_descriptions(step: dict[str, Any]) -> bool:
    if step.get("twilio_list_use_descriptions"):
        return True
    sid = _resolve_content_sid(step)
    return bool(sid and sid in _variable_mcq_content_sids())


def _twilio_list_row(text: str) -> tuple[str, str]:
    """
    WhatsApp list rows: title max 24 chars; use description (max 72) for full option text.
    """
    full = (text or "").strip() or "Option"
    if len(full) <= WHATSAPP_LIST_TITLE_MAX:
        return full, ""
    description = full[:WHATSAPP_LIST_DESCRIPTION_MAX]
    title = full[:WHATSAPP_LIST_TITLE_MAX]
    if " " in title:
        trimmed = title.rsplit(" ", 1)[0]
        if len(trimmed) >= 10:
            title = trimmed
    return title, description


def _twilio_list_label(text: str) -> str:
    """Short row title only — prefer _twilio_list_row when building Twilio variables."""
    title, _ = _twilio_list_row(text)
    return title


def _twilio_list_prompt(step: dict[str, Any]) -> str:
    """Single-line list body — use twilio_list_prompt or the last non-empty line of prompt."""
    if step.get("twilio_list_prompt"):
        return str(step["twilio_list_prompt"]).strip()
    raw = str(step.get("prompt") or "Please choose one option.").strip()
    lines = [ln.strip() for ln in raw.split("\n") if ln.strip()]
    return lines[-1] if lines else "Please choose one option."


def _build_content_variables(step: dict[str, Any], options: list[dict[str, Any]]) -> dict[str, str]:
    """
    Build variables for Twilio list-picker templates.
    Only sends variables for filled options — never pads empty rows.
    """
    from backend.schemas.service import WHATSAPP_SERVICE_LIST_ROWS

    quick_opts = [o for o in options if not _is_other_option(o)]
    if step.get("use_dynamic_list"):
        slot_count = WHATSAPP_SERVICE_LIST_ROWS
    elif step.get("twilio_list_slots"):
        slot_count = int(step["twilio_list_slots"])
    else:
        slot_count = len(quick_opts)

    variables: dict[str, str] = {"prompt": _twilio_list_prompt(step)}
    for i in range(1, slot_count + 1):
        if i > len(quick_opts):
            break
        opt = quick_opts[i - 1]
        label_src = str(opt.get("whatsapp_label") or opt.get("label") or "")
        title, description = _twilio_list_row(label_src)
        variables[f"option_{i}_label"] = title
        variables[f"option_{i}_value"] = str(opt.get("value") or opt.get("label") or f"opt_{i}").strip()
        if step.get("twilio_list_use_descriptions") or step.get("use_dynamic_list"):
            variables[f"option_{i}_description"] = description
    return variables


async def _send_interactive_options(
    to: str,
    body: str,
    options: list[dict[str, Any]],
    *,
    step: dict[str, Any],
) -> bool:
    """Send interactive WhatsApp options via Twilio Content API."""
    content_sid = _resolve_content_sid(step)
    if not content_sid:
        return False
    client = _get_client()
    if not client:
        return False
    require_variables = bool(
        step.get("require_content_variables")
        or step.get("use_dynamic_list")
        or str(step.get("field", "")) == "service_category"
        or str(step.get("field", "")).startswith("service_q")
    )
    try:
        import asyncio
        loop = asyncio.get_event_loop()
        content_variables = _build_content_variables(step, options)

        def _create_with_variables():
            return client.messages.create(
                from_=settings.twilio_whatsapp_from,
                to=to,
                content_sid=content_sid,
                content_variables=json.dumps(content_variables),
            )

        def _create_without_variables():
            return client.messages.create(
                from_=settings.twilio_whatsapp_from,
                to=to,
                content_sid=content_sid,
            )

        try:
            await loop.run_in_executor(None, _create_with_variables)
        except Exception as inner:
            err = str(inner)
            if require_variables:
                print(f"[Twilio] Interactive (variables required) failed: {err}")
                return False
            if "Content Variables parameter is invalid" not in err:
                raise
            await loop.run_in_executor(None, _create_without_variables)
        return True
    except Exception as e:
        print(f"[Twilio] Interactive send error: {e}")
        return False


async def _send_once(client, to: str, body: str, session_id: str = ""):
    import asyncio
    loop = asyncio.get_event_loop()

    def _create():
        msg = client.messages.create(
            from_=settings.twilio_whatsapp_from,
            to=to,
            body=body,
        )
        print(f"[Twilio] API Response | SID: {msg.sid} | Status: {msg.status}")
        return msg

    await loop.run_in_executor(None, _create)


def twiml_response(body: str) -> str:
    safe = body.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        "<Response><Message>" + safe + "</Message></Response>"
    )

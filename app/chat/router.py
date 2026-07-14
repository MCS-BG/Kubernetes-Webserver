from __future__ import annotations

import anthropic
from fastapi import APIRouter, HTTPException

from app.api.schemas import ChatRequest
from app.chat.agent import reset_session, send_message

router = APIRouter()


@router.post("/chat")
def chat(request: ChatRequest):
    try:
        reply = send_message(request.session_id, request.message)
    except anthropic.AuthenticationError as exc:
        raise HTTPException(
            500, "Chat agent is not configured (missing or invalid ANTHROPIC_API_KEY)"
        ) from exc
    except anthropic.RateLimitError as exc:
        raise HTTPException(429, "Chat agent is rate-limited, try again shortly") from exc
    except anthropic.APIConnectionError as exc:
        raise HTTPException(502, "Could not reach the Claude API") from exc
    except anthropic.APIStatusError as exc:
        raise HTTPException(502, f"Claude API error: {exc.message}") from exc
    except (anthropic.AnthropicError, TypeError) as exc:
        # Covers configuration errors the SDK raises before any HTTP call --
        # e.g. no ANTHROPIC_API_KEY / ANTHROPIC_AUTH_TOKEN / auth profile
        # resolvable, which surfaces as a bare TypeError, not an APIStatusError.
        raise HTTPException(500, f"Chat agent is not configured: {exc}") from exc
    return {"reply": reply}


@router.post("/chat/{session_id}/reset")
def chat_reset(session_id: str):
    reset_session(session_id)
    return {"status": "ok"}

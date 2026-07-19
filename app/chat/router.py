from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.api.schemas import ChatRequest
from app.chat.agent import reset_session, send_message
from app.chat.providers import (
    ChatProviderAuthError,
    ChatProviderConnectionError,
    ChatProviderError,
    ChatProviderRateLimitError,
)

router = APIRouter()


@router.post("/chat")
def chat(request: ChatRequest):
    try:
        reply = send_message(request.session_id, request.message)
    except ChatProviderAuthError as exc:
        raise HTTPException(500, f"Chat agent is not configured: {exc}") from exc
    except ChatProviderRateLimitError as exc:
        raise HTTPException(429, "Chat agent is rate-limited, try again shortly") from exc
    except ChatProviderConnectionError as exc:
        raise HTTPException(502, f"Could not reach the chat provider: {exc}") from exc
    except ChatProviderError as exc:
        raise HTTPException(502, f"Chat provider error: {exc}") from exc
    return {"reply": reply}


@router.post("/chat/{session_id}/reset")
def chat_reset(session_id: str):
    reset_session(session_id)
    return {"status": "ok"}

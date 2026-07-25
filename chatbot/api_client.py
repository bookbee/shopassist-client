"""HTTP client for the remote chatbot API Gateway.

This is the only component in the application that talks to a real network
service. Everything else in the store is mocked. The gateway contract below
is copied field-for-field from the real shopassist backend's Pydantic
schemas (api/schemas.py: ChatRequest / ChatResponse):

    POST {API_BASE_URL}/api/v1/chat
    Header: X-API-Key: {settings.api_key}  (see shopassist's api/security.py)
    -> {"session_id": "abc123", "user_id": "alum-1001", "text": "Where is my order?", "source_channel": "web_chat"}
    <- {"session_id": "abc123", "response_text": "...", "agent_invoked": "OrderTrackingAgent",
        "confidence_score": 0.9, "timestamp": "2026-07-13T10:15:00Z"}

If agent_invoked == "EscalationAgent" the UI opens the support ticket flow.
The real backend has no ticket concept at the API layer, so the ticket
shown to the customer is always synthesised client-side (see
chatbot/chat_ui.py::_new_ticket) — this holds whether talking to
mock_gateway.py or the real service.
"""
from __future__ import annotations

import json

import requests

from chatbot.models import ChatRequest, ChatResponse
from config import settings
from utils.helpers import get_logger

log = get_logger("alumni_store.chat")

UNAVAILABLE_MESSAGE = "AI Assistant is currently unavailable."


def send_message(session_id: str, user_id: str, message: str, source_channel: str = "web_chat") -> ChatResponse:
    """POST the user's message to the gateway and normalise the reply.

    Never raises — every failure mode collapses to ChatResponse(ok=False)
    so the UI can degrade gracefully instead of crashing.
    """
    request = ChatRequest(session_id=session_id, user_id=user_id, text=message, source_channel=source_channel)
    url = settings.chat_url
    request_json = request.to_json()
    log.debug("Chat request -> %s: %s", url, request_json)
    try:
        headers = {"Content-Type": "application/json"}
        if settings.api_key:
            headers["X-API-Key"] = settings.api_key
        response = requests.post(
            url,
            json=request_json,
            timeout=settings.timeout_seconds,
            headers=headers,
        )
        log.debug("Chat response <- %s %s: %s", response.status_code, url, response.text)
        response.raise_for_status()
    except requests.exceptions.Timeout:
        log.warning("Chat gateway timeout after %ss (%s)", settings.timeout_seconds, url)
        return ChatResponse(ok=False)
    except requests.exceptions.ConnectionError:
        log.warning("Chat gateway unreachable (%s)", url)
        return ChatResponse(ok=False)
    except requests.exceptions.HTTPError as exc:
        log.error("Chat gateway HTTP error: %s | body: %s", exc, response.text)
        return ChatResponse(ok=False)
    except requests.exceptions.RequestException as exc:
        log.error("Chat gateway request failed: %s", exc)
        return ChatResponse(ok=False)

    try:
        payload = response.json()
    except (json.JSONDecodeError, ValueError) as exc:
        log.error("Chat gateway returned invalid JSON: %s", exc)
        return ChatResponse(ok=False)

    if not isinstance(payload, dict):
        log.error("Chat gateway returned non-object JSON: %r", payload)
        return ChatResponse(ok=False)

    reply = str(payload.get("response_text", "")).strip()
    agent_invoked = payload.get("agent_invoked")
    confidence_score = float(payload.get("confidence_score") or 0.0)
    resolved_session_id = str(payload.get("session_id") or session_id)
    ticket = payload.get("ticket") if isinstance(payload.get("ticket"), dict) else None

    log.info("Chat ok | agent=%s | confidence=%.2f | %d chars", agent_invoked, confidence_score, len(reply))
    return ChatResponse(
        ok=True,
        session_id=resolved_session_id,
        reply=reply,
        agent_invoked=agent_invoked,
        confidence_score=confidence_score,
        ticket=ticket,
        raw=payload,
    )

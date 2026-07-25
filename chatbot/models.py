"""Typed models for the chatbot layer.

Field-for-field mirror of the real shopassist API Gateway's Pydantic schemas
(shopassist/api/schemas.py: ChatRequest / ChatResponse) so this layer speaks
the same contract whether it's pointed at mock_gateway.py or the real
FastAPI service — swapping API_BASE_URL is the only change either way.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class ChatRequest:
    """Payload sent to the API Gateway — matches shopassist's ChatRequest."""

    session_id: str
    user_id: str
    text: str
    source_channel: str = "web_chat"

    def to_json(self) -> dict[str, str]:
        return {
            "session_id": self.session_id,
            "user_id": self.user_id,
            "text": self.text,
            "source_channel": self.source_channel,
        }


@dataclass
class ChatResponse:
    """Normalised response from the API Gateway — matches shopassist's ChatResponse.

    ok=False means the gateway was unreachable or returned garbage; the UI
    then shows the graceful "assistant unavailable" message. `ticket` is
    populated client-side when absent (the real backend has no ticket
    concept at the API layer — see chatbot/chat_ui.py::_new_ticket).
    """

    ok: bool
    session_id: str = ""
    reply: str = ""
    agent_invoked: Optional[str] = None
    confidence_score: float = 0.0
    ticket: Optional[dict[str, Any]] = None
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def is_escalation(self) -> bool:
        return self.agent_invoked == "EscalationAgent"

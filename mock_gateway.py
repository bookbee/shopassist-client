"""Local stand-in for the real shopassist API Gateway (stdlib only, no deps).

The client app's chatbot POSTs to {API_BASE_URL}/api/v1/chat. This file
answers that request/response contract exactly as the real shopassist
FastAPI backend does (shopassist/api/schemas.py: ChatRequest / ChatResponse,
shopassist/api/routers/chat.py):

    -> {"session_id": ..., "user_id": ..., "text": ..., "source_channel": "web_chat"}
    <- {"session_id": ..., "response_text": ..., "agent_invoked": "OrderTrackingAgent",
        "confidence_score": 0.9, "timestamp": "2026-07-13T10:15:00+00:00"}

`agent_invoked` is always one of the five agents the real orchestrator
registers: OrderTrackingAgent, ProductRecommendationAgent, ReturnsAgent,
GeneralPurposeAgent, EscalationAgent — see shopassist/services/orchestrator.py.
There is no "ticket" field in the real response; on escalation the
client synthesises a ticket number itself (chatbot/chat_ui.py::
_new_ticket), so this mock deliberately doesn't send one either — that
path needs to work identically against both.

Run this in a second terminal for local end-to-end demos:

    python mock_gateway.py            # serves http://localhost:8000

To switch to the real gateway: stop this process and, from the shopassist
repo, run `uvicorn api.main:app --host 0.0.0.0 --port 8000` instead — same
port, same path, same request/response shape. The client app needs no
code changes either way; only API_BASE_URL in .env decides which one it's
talking to (and both being on :8000, not even that needs to change).
"""
from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

HOST, PORT = "localhost", 8000
PROFILE_PATH = Path(__file__).resolve().parent / "data" / "profile.json"

# Sessions already greeted this process's lifetime — lets the mock
# personalise only the *opening* line of a conversation instead of every
# turn (a real backend would check "is conversation_history for this
# session empty?"; this mock approximates that in memory since it has no
# real session store).
SEEN_SESSIONS: set[str] = set()


def _customer_name() -> str:
    """Look up the logged-in customer's display name.

    A real backend would key this off `user_id` against a customers table
    (see shopassist-database) and return a real name. This demo only has
    one profile, so it just reads the same data/profile.json the client
    app itself renders on the profile page.

    Deliberately NOT derived from session_id — that field only correlates
    turns within one conversation (and the mock mints a fresh one whenever
    the caller omits it, same as the real backend). Treating it as a name
    is a real bug in shopassist's services/llm_inference.py::call_generative
    (`session_id.split('_')[0]`), which is how you get a bot that says
    "Hello session!" instead of a customer's actual name.
    """
    try:
        profile = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
        name = str(profile.get("name", "")).strip()
        if name:
            return name.split()[0]
    except (OSError, json.JSONDecodeError):
        pass
    return "there"

PRODUCT_FACTS = {
    "hoodie": "The Alumni Hoodie is 80% cotton / 20% polyester fleece at 320 GSM, "
              "brushed inside, with an embroidered chest wordmark. Sizes S–XXL.",
    "t-shirt": "The Classic T-Shirt is 100% combed cotton, 180 GSM, bio-washed, "
               "with a screen-printed gold crest. Sizes S–XXL.",
    "mug": "The Crest Ceramic Mug holds 330 ml and is microwave and dishwasher safe.",
    "flask": "The Insulated Coffee Flask keeps drinks hot 12 hours and cold 24 hours (500 ml).",
    "bottle": "The Steel Water Bottle is 750 ml, food-grade 304 stainless steel, "
              "leak-proof but not insulated.",
}

GIFTS_UNDER_1000 = (
    "Under ₹1000, alumni favourites are: the Alumni Lapel Badge (₹299), "
    "Tata Hall Notebook (₹249), Crest Ceramic Mug (₹349), Heritage Cap (₹449), "
    "Classic T-Shirt (₹599), and the Executive Pen Set (₹999) if you want a boxed gift."
)

SIZE_GUIDE = (
    "Our apparel runs true to size with a relaxed fit. Chest measurements: "
    "S 38\", M 40\", L 42\", XL 44\", XXL 46\". If you're between sizes on the "
    "t-shirt, size down; for the hoodie, stay with your usual size."
)

ORDER_ID_PATTERN = re.compile(r"iisc\d{9,}", re.IGNORECASE)

# Every branch maps onto one of the five agents the real orchestrator
# registers (services/orchestrator.py) — the taxonomy the UI will actually
# see is identical whether talking to this mock or the real backend, even
# though this mock's keyword routing is far coarser than a real LLM router.
AGENT_ORDER_TRACKING = "OrderTrackingAgent"
AGENT_PRODUCT_RECOMMENDATION = "ProductRecommendationAgent"
AGENT_RETURNS = "ReturnsAgent"
AGENT_GENERAL_PURPOSE = "GeneralPurposeAgent"
AGENT_ESCALATION = "EscalationAgent"


def route(message: str) -> dict:
    """Very small intent router for demo purposes.

    Returns {"agent_invoked", "reply", "confidence"} — the handler wraps
    this into the full ChatResponse-shaped envelope.
    """
    text = message.lower()

    order_match = ORDER_ID_PATTERN.search(text)
    if order_match or "where is my order" in text or "track" in text:
        order_id = order_match.group(0).upper() if order_match else "your latest order"
        return {
            "agent_invoked": AGENT_ORDER_TRACKING,
            "confidence": 0.9,
            "reply": f"Order {order_id} is out for delivery and should reach you "
                     "by tomorrow evening. You'll get an SMS when the courier is nearby.",
        }

    if "escalate" in text or "human" in text or "customer support" in text or "talk to" in text:
        return {
            "agent_invoked": AGENT_ESCALATION,
            "confidence": 0.95,
            "reply": "I've connected you to our support team — a specialist will "
                     "take it from here.",
        }

    if "return" in text or "refund" in text:
        return {
            "agent_invoked": AGENT_RETURNS,
            "confidence": 0.85,
            "reply": "You can return any unused item within 14 days of delivery. "
                     "Go to Orders → select the order → Return, or share the order "
                     "ID here and I'll start it for you. Refunds land in 5–7 business days.",
        }

    if "payment" in text and ("fail" in text or "declin" in text or "stuck" in text):
        return {
            "agent_invoked": AGENT_GENERAL_PURPOSE,
            "confidence": 0.6,
            "reply": "Sorry about that — failed payments auto-reverse within 3–5 "
                     "business days and no order is created. If the amount was "
                     "debited, share the transaction reference and I'll flag it.",
        }

    if "size" in text:
        return {"agent_invoked": AGENT_GENERAL_PURPOSE, "confidence": 0.75, "reply": SIZE_GUIDE}

    if "deliver" in text or "arrive" in text or "shipping" in text:
        return {
            "agent_invoked": AGENT_GENERAL_PURPOSE,
            "confidence": 0.7,
            "reply": "Metro cities take 3–5 business days; the rest of India 5–8. "
                     "Orders above ₹999 ship free.",
        }

    if "gift" in text or "suggest" in text or "recommend" in text or "below" in text:
        return {"agent_invoked": AGENT_PRODUCT_RECOMMENDATION, "confidence": 0.8, "reply": GIFTS_UNDER_1000}

    for keyword, fact in PRODUCT_FACTS.items():
        if keyword in text:
            return {"agent_invoked": AGENT_GENERAL_PURPOSE, "confidence": 0.75, "reply": fact}

    if any(g in text for g in ("hello", "hi", "hey", "namaste")):
        return {
            "agent_invoked": AGENT_GENERAL_PURPOSE,
            "confidence": 0.6,
            # No leading "Hello!" here — the handler already prefixes the
            # first turn of a session with "Hi {name}!" below.
            "reply": "I'm the Alumni Store assistant. I can track orders, "
                     "answer product questions, help with returns, or suggest gifts. "
                     "What can I do for you?",
        }

    return {
        "agent_invoked": AGENT_GENERAL_PURPOSE,
        "confidence": 0.3,
        "reply": "I can help with order tracking, product details, sizing, delivery, "
                 "returns, payments, and gift ideas. Could you rephrase, or say "
                 "'customer support' to reach a human?",
    }


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):  # noqa: N802 — http.server API
        if self.path != "/api/v1/chat":
            self.send_error(404, "Unknown endpoint")
            return
        try:
            length = int(self.headers.get("Content-Length", 0))
            payload = json.loads(self.rfile.read(length) or b"{}")
            message = str(payload.get("text", ""))
        except (ValueError, json.JSONDecodeError):
            self.send_error(400, "Invalid JSON")
            return

        session_id = payload.get("session_id") or f"session_{uuid.uuid4().hex[:12]}"
        print(
            f"[mock-gateway] session={session_id} "
            f"user={payload.get('user_id')} channel={payload.get('source_channel')}"
        )

        routed = route(message)
        reply_text = routed["reply"]

        is_first_turn = session_id not in SEEN_SESSIONS
        SEEN_SESSIONS.add(session_id)
        if is_first_turn:
            reply_text = f"Hi {_customer_name()}! {reply_text}"

        response_body = {
            "session_id": session_id,
            "response_text": reply_text,
            "agent_invoked": routed["agent_invoked"],
            "confidence_score": routed["confidence"],
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        body = json.dumps(response_body).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):  # quieter console
        print(f"[mock-gateway] {fmt % args}")


if __name__ == "__main__":
    print(f"Mock API Gateway (shopassist-schema-compatible) listening on http://{HOST}:{PORT}/api/v1/chat")
    HTTPServer((HOST, PORT), Handler).serve_forever()

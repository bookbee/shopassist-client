# shopassist-client

Streamlit web client for ShopAssist — the "IISc Alumni Store" merchandise
portal (catalog, cart, checkout, orders, profile) plus a floating AI
assistant that talks to the `shopassist` backend over one HTTP endpoint.

- **Streamlit/web developers** own this whole repo — see "For UI
  developers" below to run it and find your way around.
- **Anyone integrating with the API** only needs "Chat API contract"
  below to keep `shopassist`'s `/api/v1/chat` endpoint compatible with
  this client.

## For UI developers

### Setup & run

Requires Python 3.12 (3.10+ should work).

```bash
git clone https://github.com/bookbee/shopassist-client
cd shopassist-client
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

Log in with any user ID/password (demo auth only — nothing is checked).
The chat widget needs a gateway on `API_BASE_URL`; for local demos, run the
included stdlib mock in a second terminal:

```bash
python mock_gateway.py     # serves http://localhost:8000/api/v1/chat
```

Then try: "Where is order ord-1001?", "What size should I buy?", "I
want to talk to customer support" (triggers the ticket flow). First
message of a session gets a "Hi \<name\>!" greeting from
`data/profile.json`.

To point at the real gateway instead: stop `mock_gateway.py`, start
`shopassist`'s FastAPI service on the same port — no code or config change
needed here.

### Running with Docker

```bash
docker compose up -d --build
```

Builds and runs this container standalone (image/container
`shopassist-client`), talking to the API on the host via
`host.docker.internal`. Override the published port with `WEB_PORT`
(defaults to 8501).

To run the whole platform together (Postgres, Ollama, the API, and this
storefront) with one command instead, use
[shopassist-devops](../shopassist-devops) — its `docker compose up`
`include:`s this file unmodified and wires everything onto one shared
container network.

### Configuration

`.env` (gitignored) — falls back to `config.yaml`, then a hardcoded
default:

```env
API_BASE_URL=http://localhost:8000
TIMEOUT=10
APP_TITLE=IISc Alumni Store
ENABLE_CHATBOT=true
LOG_LEVEL=INFO
```

`config.yaml` also holds the storefront palette and chat endpoint path —
stable enough that they're not worth exposing as env vars.

### Project structure

```text
shopassist-client/
├── app.py                  entrypoint + router + CSS/logo injection
├── config.py / config.yaml settings (env-overridable)
├── mock_gateway.py         local stand-in for the API Gateway
├── pages/                  login, home, catalog, product, cart, checkout, orders, profile, about
├── components/             navbar, footer, product_card, cart_widget
├── chatbot/                api_client.py + models.py (API integration, see below) and chat_ui.py (UI)
├── data/                   products, orders, profile, faq, announcements — all JSON
├── utils/                  helpers, constants
├── styles/styles.css       theme, chat panel, chat logo/watermark
├── assets/                 logo (+ logo_small.png for CSS use), banners, product images
├── Dockerfile / docker-compose.yml  standalone container build/run
└── logs/app.log
```

### Chatbot UI

- `chatbot/chat_ui.py` renders the floating launcher and panel
  (`st.popover`) — all Streamlit-specific rendering lives here.
- `chatbot/api_client.py` + `chatbot/models.py` have zero Streamlit
  dependency — see "Chat API contract" below; keep these in sync with the
  backend, not with the UI.
- Branding: the round badge next to "Alumni Store Assistant" and the faint
  watermark behind the message history are both driven by `--brand-logo`,
  a CSS variable set from `assets/logo_small.png` in `app.py::load_css()`
  — swap that file to rebrand.
- Panel sizing is in `styles/styles.css`
  (`div[data-testid="stPopoverBody"]:has(.chat-panel-marker)`) — tall
  enough that the history pane, quick-action prompts, and input row all
  fit on open without an inner scrollbar on a typical viewport.

### Logging

Rotating log at `logs/app.log` (`LOG_LEVEL=DEBUG` for full chat
request/response bodies). Chat failures (timeout, bad JSON, non-2xx) all
collapse to the same in-chat "unavailable" message — never a raw error.

### Known issues

- `mock_gateway.py` and a real `uvicorn` instance of the shopassist API
  can't both hold port 8000 — check `lsof -i :8000` if chat looks wrong.
- Don't `rm logs/app.log` while the app is running — restart it instead;
  the running process keeps writing to the deleted file's old inode.

## Chat API contract

The only integration surface between this client and the `shopassist`
backend. Copied field-for-field from its Pydantic schemas
(`api/schemas.py`) — `mock_gateway.py` and the real service are
interchangeable without touching this repo's code.

Request:

```json
{ "session_id": "abc123", "user_id": "alum-1001", "text": "Where is my order?", "source_channel": "web_chat" }
```

Response:

```json
{ "session_id": "abc123", "response_text": "...", "agent_invoked": "OrderTrackingAgent",
  "confidence_score": 0.9, "timestamp": "2026-07-13T10:15:00+00:00" }
```

Behavior this client relies on:

- `session_id` is opaque — minted client-side, echoed back unchanged on
  every turn. It never encodes anything (not a user's name, nothing).
- `agent_invoked == "EscalationAgent"` triggers the support-ticket UI.
  There's no `ticket` field in the response — the backend has no ticket
  concept at the API layer, so the number/response-time shown to the
  customer is always synthesised client-side
  (`chatbot/chat_ui.py::_new_ticket`).
- First-turn-only personalized greeting is the backend's job — this
  client just renders whatever `response_text` says.
- Any failure (timeout, non-2xx, malformed JSON) must be safe to degrade
  to a generic message — this client never surfaces a stack trace.

## Not done yet

- Real authentication (alumni SSO) and member pricing
- Payment gateway integration at the mocked checkout step
- `data/*.json` → a real database/inventory service (see
  `shopassist-database`)
- Token-by-token streaming over SSE/WebSocket
- Wishlist persistence, dark mode, i18n
- Publish the `shopassist-client` image to a registry

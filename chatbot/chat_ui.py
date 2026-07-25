"""AI Assistant — the capstone's headline feature.

A prominent launcher pill sits fixed at the bottom-right of every page
(styled via the .st-key-chat_launcher CSS hook). Clicking it opens the
conversation inline as an anchored floating panel (st.popover) — the
page underneath stays visible and interactive, so it reads as part of
the storefront chrome rather than an interruption.

Sending a message is two-phase: the widget callback (_enqueue) just stores
it and marks it pending, so the panel stays open and a typing indicator can
render; the actual (blocking) call to the remote API Gateway happens right
after in the normal script body (_resolve_pending), via chatbot.api_client.
An agent_invoked == "EscalationAgent" response triggers the support-ticket
flow.
"""
from __future__ import annotations

import html
import random
import string
import time

import streamlit as st

from chatbot.api_client import UNAVAILABLE_MESSAGE, send_message
from chatbot.models import ChatResponse
from config import settings
from utils.constants import CHAT_QUICK_ACTIONS, TICKET_RESPONSE_TIME
from utils.helpers import get_logger

log = get_logger("alumni_store.chat_ui")

# Typewriter reveal for freshly-arrived bot replies (see _stream_bot_reply).
_STREAM_WORDS_PER_TICK = 1
_STREAM_TICK_SECONDS = 0.05


def _new_ticket(response: ChatResponse) -> dict:
    ticket = response.ticket or {}
    return {
        "number": ticket.get(
            "number", "TCK-" + "".join(random.choices(string.digits, k=6))
        ),
        "response_time": ticket.get("response_time", TICKET_RESPONSE_TIME),
    }


def _push(role: str, content: str, meta: dict | None = None) -> None:
    meta = dict(meta or {})
    if role == "bot":
        meta.setdefault("streamed", False)
    st.session_state.chat_history.append(
        {"role": role, "content": content, "meta": meta}
    )


def _enqueue(message: str) -> None:
    """Widget callback: record the user's turn and mark it pending.

    The actual network call happens in _resolve_pending() from the normal
    script body, not here. Streamlit executes on_click/on_submit callbacks
    in a separate pass before the script reruns and starts painting, so
    anything the callback itself renders never reaches the browser until
    after it returns — there'd be nothing to show a typing indicator with
    if the (blocking) send_message() call also lived here.
    """
    message = message.strip()
    if not message:
        return
    _push("user", message)
    st.session_state.chat_pending = message


def _resolve_pending() -> None:
    """Send the pending message and push the reply — runs in the main
    script body, immediately after the typing indicator has been drawn
    (see _chat_panel), so that indicator actually reaches the browser
    before this blocks on the network request.
    """
    message = st.session_state.pop("chat_pending", None)
    if not message:
        return

    response = send_message(
        st.session_state.chat_session_id,
        st.session_state.user_id,
        message,
    )

    if not response.ok:
        _push("bot", UNAVAILABLE_MESSAGE, {"error": True})
        return

    if response.is_escalation:
        ticket = _new_ticket(response)
        st.session_state.last_ticket = ticket
        reply = response.reply or "I've raised this with our support team."
        _push("bot", reply, {"escalated": True, "ticket": ticket})
        return

    _push("bot", response.reply or "…", {"agent_invoked": response.agent_invoked})


# --------------------------------------------------------------------------- #
# Widget callbacks (run before the rerun, so the dialog stays open)
# --------------------------------------------------------------------------- #
def _on_form_send() -> None:
    _enqueue(st.session_state.get("chat_text", ""))


def _on_quick_action(prompt: str) -> None:
    _enqueue(prompt)


def _on_clear() -> None:
    st.session_state.chat_history = []
    st.session_state.chat_pending = None


# --------------------------------------------------------------------------- #
# Panel
# --------------------------------------------------------------------------- #
def _bot_bubble_html(content: str, *, cursor: bool = False) -> str:
    safe = html.escape(content).replace("\n", "<br>")
    suffix = " <span class='chat-cursor'></span>" if cursor else ""
    return f"<div class='chat-bot'>{safe}{suffix}</div>"


def _stream_bot_reply(msg: dict) -> None:
    """Reveal a freshly-arrived bot reply word by word, typewriter-style.

    Runs once per message, guarded by meta['streamed'] - _render_history()
    re-runs on every app rerun (any widget interaction anywhere on the
    page), not just on new chat turns, so without the guard old replies
    would replay their animation every time the page reruns.
    """
    words = msg["content"].split(" ")
    placeholder = st.empty()
    for i in range(0, len(words), _STREAM_WORDS_PER_TICK):
        shown = " ".join(words[: i + _STREAM_WORDS_PER_TICK])
        placeholder.markdown(_bot_bubble_html(shown, cursor=True), unsafe_allow_html=True)
        time.sleep(_STREAM_TICK_SECONDS)
    placeholder.markdown(_bot_bubble_html(msg["content"]), unsafe_allow_html=True)
    msg["meta"]["streamed"] = True


def _render_history() -> None:
    if not st.session_state.chat_history:
        st.markdown(
            "<div class='chat-bot'>Namaste! I can track orders, explain products, "
            "suggest gifts, or connect you to support. How can I help?</div>",
            unsafe_allow_html=True,
        )
        return

    history = st.session_state.chat_history[-30:]
    last_index = len(history) - 1
    for i, msg in enumerate(history):
        if msg["role"] == "user":
            safe = html.escape(msg["content"]).replace("\n", "<br>")
            st.markdown(f"<div class='chat-user'>{safe}</div>", unsafe_allow_html=True)
            continue

        meta = msg.get("meta", {})
        if i == last_index and not meta.get("streamed"):
            _stream_bot_reply(msg)
        else:
            st.markdown(_bot_bubble_html(msg["content"]), unsafe_allow_html=True)

        if meta.get("escalated"):
            ticket = meta["ticket"]
            st.success(
                f"**Support Ticket Created**\n\n"
                f"Ticket number: `{ticket['number']}`\n\n"
                f"Expected response time: {ticket['response_time']}"
            )


def _chat_panel() -> None:
    # Client portals the popover body outside .st-key-chat_launcher, so this
    # marker lets styles.css scope itself via :has() instead of descendant nesting.
    st.markdown("<div class='chat-panel-marker'></div>", unsafe_allow_html=True)
    st.markdown(
        "<div class='chat-header'><span class='chat-logo'></span>"
        "<span class='chat-header-title'>Alumni Store Assistant</span></div>",
        unsafe_allow_html=True,
    )
    st.caption("Order tracking, product Q&A, and support — one chat.")

    with st.container(height=260, border=False, key="chat_history"):
        _render_history()
        if st.session_state.get("chat_pending"):
            st.markdown(
                "<div class='chat-bot chat-typing'><span></span><span></span><span></span></div>",
                unsafe_allow_html=True,
            )

    if st.session_state.get("chat_pending"):
        _resolve_pending()
        st.rerun()

    if not st.session_state.chat_history:
        st.markdown("<div class='chat-agent'>Try asking</div>", unsafe_allow_html=True)
        qa_cols = st.columns(2)
        for i, prompt in enumerate(CHAT_QUICK_ACTIONS):
            qa_cols[i % 2].button(
                prompt,
                key=f"qa_{i}",
                width="stretch",
                on_click=_on_quick_action,
                args=(prompt,),
            )

    with st.form("chat_form", clear_on_submit=True, border=False):
        text_col, send_col = st.columns([4, 1])
        text_col.text_input(
            "Message",
            key="chat_text",
            placeholder="e.g. Where is order ord-1001?",
            label_visibility="collapsed",
        )
        send_col.form_submit_button("Send", type="primary", on_click=_on_form_send,
                                    width="stretch")

    if st.session_state.chat_history:
        st.button("Clear conversation", key="chat_clear", on_click=_on_clear)


def render_chatbot() -> None:
    """Render the fixed launcher; opens an anchored panel in place. Call once per run."""
    if not settings.enable_chatbot:
        return
    with st.popover("💬 Ask the Assistant", key="chat_launcher"):
        _chat_panel()

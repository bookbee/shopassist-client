"""Voice-input mic button for the chat panel (chatbot/chat_ui.py).

Wraps a small hand-rolled Streamlit component (voice_input/frontend/index.html)
that transcribes speech to text via the browser's native Web Speech API and
reports the transcript back here. See that file's own docstring for why it's
plain HTML/JS rather than a build step, and for the browser-support fallback
(the button simply doesn't render on Safari/Firefox today).

Streamlit component values are sticky across reruns, not one-shot events -
the same transcript would otherwise get treated as a fresh message on every
unrelated rerun of the page (resizing the panel, sending a text message,
etc.). voice_input() below guards against that by comparing the frontend's
per-result id against the last one seen (session_state), only returning a
transcript the first time each id is observed.
"""
from __future__ import annotations

import os

import streamlit as st
import streamlit.components.v1 as components

_FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "voice_input", "frontend")
_component = components.declare_component("voice_input", path=_FRONTEND_DIR)


def voice_input(key: str, disabled: bool = False) -> str | None:
    """Renders the mic button. Returns a freshly-transcribed message the one
    time it arrives, and None on every other rerun (including reruns where
    the same result is still the component's current value).

    disabled: mirrors the Send button/quick-actions' own `disabled=pending`
    (chat_ui.py) - stops a voice message from starting mid-request."""
    result = _component(key=key, default=None, disabled=disabled)
    if not result:
        return None

    seen_key = f"_voice_input_seen_id::{key}"
    if result.get("id") == st.session_state.get(seen_key):
        return None  # same result as last time - already handled, not new

    st.session_state[seen_key] = result.get("id")
    text = (result.get("text") or "").strip()
    return text or None

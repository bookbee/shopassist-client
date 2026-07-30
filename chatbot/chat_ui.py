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
from streamlit.components.v1 import html as components_html

from chatbot.api_client import UNAVAILABLE_MESSAGE, send_message
from chatbot.models import ChatResponse
from chatbot.voice_input import voice_input
from config import settings
from utils.constants import CHAT_QUICK_ACTIONS, TICKET_RESPONSE_TIME
from utils.helpers import forget_chat_history, get_logger, get_or_create_chat_history

log = get_logger("alumni_store.chat_ui")

# Typewriter reveal for freshly-arrived bot replies (see _stream_bot_reply).
_STREAM_WORDS_PER_TICK = 1
_STREAM_TICK_SECONDS = 0.05

# History pane height (px) - normal vs. expanded (toggled via the panel's
# resize button, see _on_toggle_size). Kept constant regardless of message/
# quick-action/clear-button state so the panel never visibly resizes on its
# own - see _chat_panel()'s docstring.
_HISTORY_HEIGHT_NORMAL = 340
_HISTORY_HEIGHT_EXPANDED = 560

# Scrolls .st-key-chat_history to its bottom whenever its content changes -
# new turns, the typing indicator, and each word of the typewriter reveal
# alike - via a MutationObserver reaching into the parent document (a
# components.html iframe is same-origin with the Streamlit page, so this is
# safe). Placed first inside the history container on every render, before
# _render_history() runs, so the observer is already attached by the time a
# freshly-arrived reply starts revealing word by word (that reveal happens
# via repeated placeholder.markdown() calls within one script run, without
# an intervening rerun - see _stream_bot_reply). Without this, a fixed-
# height history pane just sits at whatever scroll position it was left at,
# so a new user who doesn't think to scroll down can stare at the same spot
# while a reply streams in above/below the fold and never notice it arrived.
_AUTOSCROLL_JS = """
<script>
(function() {
  function scrollToBottom() {
    window.parent.document.querySelectorAll('.st-key-chat_history')
      .forEach(function(el) { el.scrollTop = el.scrollHeight; });
  }
  var target = window.parent.document.querySelector('.st-key-chat_history');
  if (target && !target.dataset.autoscrollObserved) {
    target.dataset.autoscrollObserved = "1";
    new MutationObserver(scrollToBottom)
      .observe(target, {childList: true, subtree: true, characterData: true});
  }
  scrollToBottom();
})();
</script>
"""


def _inject_autoscroll() -> None:
    components_html(_AUTOSCROLL_JS, height=0)


# Refocuses the message input the moment it flips from disabled back to
# enabled - a fresh reply just finished arriving, since the input is
# disabled for the whole pending/typing-indicator window (see _chat_panel).
# Streamlit repaints the DOM from scratch on rerun, which drops whatever the
# browser had focused, so without this the customer has to click back into
# the box before they can keep typing - exactly the "cursor isn't in the box
# after the answer comes" behaviour.
#
# A one-shot script (check once, focus if enabled) turns out not to fire
# reliably here: components.html only re-loads its iframe when the HTML it's
# given actually changes, and this string is the same every render, so the
# embedded <script> only really runs on the panel's first-ever open, not on
# every subsequent reply - the same reason _AUTOSCROLL_JS above is a
# persistent MutationObserver rather than a plain scrollToBottom() call.
# This uses the identical pattern: attach one observer to the real <input>
# (guarded by a dataset flag so a second, redundant iframe load - if one
# ever does occur - can't double-attach) that watches specifically for its
# `disabled` attribute changing, and focuses it every time that flips to
# enabled - which then keeps working for every future reply, without this
# script needing to run again itself.
#
# attach() retries for a couple of seconds if the element isn't there yet
# rather than giving up after one querySelector - this iframe's script runs
# the instant Streamlit streams it down, which can race ahead of the actual
# <textarea> being mounted (measured: the switch from text_input to
# text_area for CR2's auto-grow made this race easy to lose - the plain
# text_input this used to target apparently hydrated fast enough to usually
# win it).
_FOCUS_INPUT_JS = """
<script>
(function() {
  function attach(triesLeft) {
    var el = window.parent.document.querySelector('.st-key-chat_text textarea');
    if (!el) {
      if (triesLeft > 0) { setTimeout(function() { attach(triesLeft - 1); }, 100); }
      return;
    }
    if (el.dataset.focusRestoreObserved) { return; }
    el.dataset.focusRestoreObserved = "1";
    if (!el.disabled) { el.focus(); }
    new MutationObserver(function() {
      if (!el.disabled) { el.focus(); }
    }).observe(el, {attributes: true, attributeFilter: ['disabled']});
  }
  attach(50);
})();
</script>
"""


def _inject_focus_restore() -> None:
    components_html(_FOCUS_INPUT_JS, height=0)


# The message box is now a plain <textarea> (see _chat_panel's row 1, and
# styles.css's .st-key-chat_text rules for why - it needs to grow with a
# long message) rather than text_input's single-line <input>, so Enter no
# longer submits the form on its own - a bare <textarea> always inserts a
# newline. This restores "Enter sends, Shift+Enter inserts a newline" by
# forwarding a plain Enter onto the real, hidden form_submit_button - the
# same reach-into-the-parent-document trick _AUTOSCROLL_JS/_FOCUS_INPUT_JS
# above and the row-2 Send proxy below all use. isComposing is checked so a
# Japanese/Chinese/Korean IME's Enter-to-confirm-candidate keystroke isn't
# hijacked into sending the message mid-composition. attach() retries until
# the <textarea> exists - see _FOCUS_INPUT_JS's comment on the same race.
_TEXTAREA_ENTER_TO_SEND_JS = """
<script>
(function() {
  function attach(triesLeft) {
    var el = window.parent.document.querySelector('.st-key-chat_text textarea');
    if (!el) {
      if (triesLeft > 0) { setTimeout(function() { attach(triesLeft - 1); }, 100); }
      return;
    }
    if (el.dataset.enterToSendObserved) { return; }
    el.dataset.enterToSendObserved = "1";
    el.addEventListener('keydown', function(e) {
      if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) {
        e.preventDefault();
        var sendBtn = window.parent.document.querySelector('.st-key-chat_send_hidden button');
        if (sendBtn && !sendBtn.disabled) { sendBtn.click(); }
      }
    });
  }
  attach(50);
})();
</script>
"""


def _inject_textarea_enter_to_send() -> None:
    components_html(_TEXTAREA_ENTER_TO_SEND_JS, height=0)


# styles.css anchors the message textarea to the bottom of its own wrapper
# and lets it grow UPWARD past the wrapper's top edge (so a long message
# overlays the history pane above it instead of pushing the Clear/Send row
# down - see that CSS block's own comment). That only works if the
# wrapper's own reserved height matches what an EMPTY textarea actually
# renders at on this exact browser - get that wrong and the textarea
# overlaps upward into whatever sits above it even with nothing typed.
#
# That value can't be a hardcoded constant: it depends on real font
# metrics, which differ by device/browser/zoom/accessibility text-size
# settings - a value measured in one environment (even a real one, not a
# guess) isn't guaranteed to hold on a different device. So this measures
# it live, in the browser actually rendering the page, via el.scrollHeight
# while the box is empty - scrollHeight reports the height needed to fit
# all content with no scrolling, independent of the max-height/overflow
# CSS capping what's actually painted, so it's the same "how tall would an
# empty box naturally be" number regardless of those overrides - and
# writes it onto the wrapper as a plain inline style. styles.css's `height`
# rule on that wrapper is deliberately NOT !important so this inline style
# reliably wins over it.
#
# Re-measures whenever the box is genuinely empty again: on first attach;
# once document.fonts.ready resolves (a web font swapping in after first
# paint changes the real metrics - the plausible reason a value measured
# in one browser session didn't hold in another); on window resize
# (rewrapping at a new width can change how many lines the placeholder
# itself takes); and every time `disabled` flips back to false (a fresh
# reply just arrived and clear_on_submit already emptied the value by
# then - the same signal _FOCUS_INPUT_JS uses to restore focus at that
# same moment). attach() retries until the element exists - see
# _FOCUS_INPUT_JS's comment on the same mount race.
_TEXTAREA_COLLAPSED_HEIGHT_JS = """
<script>
(function() {
  function attach(triesLeft) {
    var el = window.parent.document.querySelector('.st-key-chat_text textarea');
    var wrap = window.parent.document.querySelector('.st-key-chat_text');
    if (!el || !wrap) {
      if (triesLeft > 0) { setTimeout(function() { attach(triesLeft - 1); }, 100); }
      return;
    }
    if (el.dataset.collapsedHeightObserved) { return; }
    el.dataset.collapsedHeightObserved = "1";

    function sync() {
      if (el.value) { return; }
      wrap.style.height = el.scrollHeight + 'px';
    }

    sync();
    if (window.parent.document.fonts) {
      window.parent.document.fonts.ready.then(sync);
    }
    var resizeTimer;
    window.parent.addEventListener('resize', function() {
      clearTimeout(resizeTimer);
      resizeTimer = setTimeout(sync, 150);
    });
    new MutationObserver(function() {
      if (!el.disabled) { sync(); }
    }).observe(el, {attributes: true, attributeFilter: ['disabled']});
  }
  attach(50);
})();
</script>
"""


def _inject_textarea_collapsed_height_sync() -> None:
    components_html(_TEXTAREA_COLLAPSED_HEIGHT_JS, height=0)


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
    """The real (but visually hidden - see styles.css's .st-key-chat_send_hidden
    rule) form_submit_button's on_click. Fires when the visible "Send" button
    in row 2 below forwards a JS-triggered click onto this real button (see
    the components.html snippet at that button's definition), or when
    _TEXTAREA_ENTER_TO_SEND_JS does the same for a plain Enter in the message
    textarea (a bare <textarea> only inserts a newline on its own - it never
    submits a form) - either way, a genuine form submission, so chat_text is
    guaranteed fresh here and clear_on_submit handles clearing it.

    Deliberately kept as a real st.form: a bare (non-form) widget's on_change
    fires on ANY blur, not just Enter - clicking Clear conversation, a quick
    action, or the mic while text sits unsent in the box would silently send
    it too. A real HTML form only submits on an explicit submit-button click
    (real or JS-proxied), which is exactly the distinction needed here."""
    _enqueue(st.session_state.get("chat_text", ""))


def _on_quick_action(prompt: str) -> None:
    _enqueue(prompt)


def _on_clear() -> None:
    forget_chat_history(st.session_state.chat_session_id)
    st.session_state.chat_history = get_or_create_chat_history(st.session_state.chat_session_id)
    st.session_state.chat_pending = None


def _on_toggle_size() -> None:
    st.session_state.chat_expanded = not st.session_state.get("chat_expanded", False)


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
            "<div class='chat-bot'>Namaste! I'm Maximus, your IISc Alumni Store assistant. "
            "I can track orders, explain products, suggest gifts, or connect you to support. "
            "How can I help?</div>",
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
    """Renders the popover body.

    The layout is deliberately arranged so its total height never changes
    on its own as a conversation progresses - quick-action prompts render
    inside the fixed-height history pane instead of being appended/removed
    below it, and "Clear conversation" is always present (disabled, not
    hidden, when there's nothing to clear yet). A panel that grows and
    shrinks as you type reads as broken even when each individual change is
    locally "correct", so every optional block lives inside a fixed-size
    area rather than adding/removing itself from the page flow.
    """
    expanded = st.session_state.get("chat_expanded", False)

    # Client portals the popover body outside .st-key-chat_launcher, so this
    # marker lets styles.css scope itself via :has() instead of descendant
    # nesting; chat-panel-expanded additionally toggles the panel's own
    # width/max-height to match the resize button below.
    marker_classes = "chat-panel-marker" + (" chat-panel-expanded" if expanded else "")
    st.markdown(f"<div class='{marker_classes}'></div>", unsafe_allow_html=True)

    header_col, resize_col = st.columns([6, 1])
    with header_col:
        st.markdown(
            "<div class='chat-header'><span class='chat-logo'></span>"
            "<span class='chat-header-title'>Alumni Store Assistant</span></div>",
            unsafe_allow_html=True,
        )
    # Pending is true for the whole (blocking) network round-trip inside
    # _resolve_pending() below. Streamlit can only apply a *new* widget
    # interaction (resize, clear, another send) by interrupting and
    # restarting this script run - and since chat_pending is popped before
    # send_message() is even called, an interruption there abandons the
    # in-flight reply after it's no longer recoverable: the customer's
    # question sits answered-never, indistinguishable from data loss, and
    # only "Clear conversation" resets it. Disabling every control that can
    # trigger a rerun for this one window closes that race entirely, rather
    # than trying to make an interrupted network call resumable.
    pending = bool(st.session_state.get("chat_pending"))

    with resize_col:
        st.button(
            "⤡" if expanded else "⤢",
            key="chat_resize_toggle",
            help="Collapse to normal size" if expanded else "Expand to a larger view",
            on_click=_on_toggle_size,
            disabled=pending,
        )
    st.caption("Order tracking, product Q&A, and support — one chat.")

    # qa_active (empty chat, greeting + quick actions) and a real
    # conversation are mutually exclusive - chat_history and the
    # quick-actions block below split one shared height budget between them
    # rather than each claiming the full amount, so the panel's total
    # height stays the same across both states instead of leaving a big
    # empty gap before the first message or clipping the buttons.
    _QA_BLOCK_HEIGHT = 150
    base_height = _HISTORY_HEIGHT_EXPANDED if expanded else _HISTORY_HEIGHT_NORMAL
    qa_active = not st.session_state.chat_history
    history_height = (base_height - _QA_BLOCK_HEIGHT) if qa_active else base_height

    with st.container(height=history_height, border=False, key="chat_history"):
        _inject_autoscroll()
        _render_history()

        if pending:
            st.markdown(
                "<div class='chat-bot chat-typing'><span></span><span></span><span></span></div>",
                unsafe_allow_html=True,
            )

    # Deliberately a sibling of chat_history above, not nested inside it.
    # Rendered unconditionally (visibility toggled by qa_active below, not
    # by adding/removing the widgets themselves) - Streamlit's stale-widget
    # cleanup for buttons inside a fixed-height scrollable container
    # doesn't reliably complete, which left these buttons visibly stuck on
    # screen after the first message when they used to live inside
    # chat_history. That same scrollable container (fixed height + the
    # autoscroll iframe's MutationObserver watching it) also turned out to
    # make a CSS-only :has() hide rule flicker back off for about a second
    # partway through a pending reply. Belt and suspenders: the qa-hidden
    # CSS class is the clean hide (removes it from layout/focus entirely),
    # and collapsing the container to 1px is a backstop so that even if
    # the CSS rule flickered the same way here, there'd be at most a
    # sliver, not a fully readable button, on screen.
    qa_hidden = "" if qa_active else " qa-hidden"
    st.markdown(f"<div class='qa-marker{qa_hidden}'></div>", unsafe_allow_html=True)
    with st.container(height=_QA_BLOCK_HEIGHT if qa_active else 1, border=False, key="chat_quick_actions"):
        st.markdown("<div class='chat-agent'>Try asking</div>", unsafe_allow_html=True)
        qa_cols = st.columns(2)
        for i, prompt in enumerate(CHAT_QUICK_ACTIONS):
            qa_cols[i % 2].button(
                prompt,
                key=f"qa_{i}",
                width="stretch",
                on_click=_on_quick_action,
                args=(prompt,),
                disabled=pending,
            )

    # Row 1: message input + mic button, mic to the right of the input.
    # text_input still lives inside a form purely so pressing Enter submits
    # it without also submitting on a plain blur (clicking Clear
    # conversation/a quick action/the mic while text sits unsent in the box)
    # - see _on_form_send's docstring. The form's own submit button is
    # visually hidden (styles.css's .st-key-chat_send_hidden rule); the
    # user-facing "Send" button lives in row 2 below as a JS proxy that
    # forwards its click onto this real one - see that button's own comment.
    #
    # Full width now that the mic lives in row 2 (see below) rather than
    # sharing this row - freeing that column for the textarea means it wraps
    # less and so needs to grow vertically less often for the same message
    # (see styles/styles.css's .st-key-chat_text overlay-growth comment).
    with st.form("chat_form", clear_on_submit=True, border=False):
        st.text_area(
            "Message",
            key="chat_text",
            placeholder="Type a message…",
            label_visibility="collapsed",
            height="content",
            disabled=pending,
        )
        st.form_submit_button("Send", key="chat_send_hidden", on_click=_on_form_send, disabled=pending)

    # Row 2: "Clear conversation" at the left corner; mic + "Send" grouped
    # together at the right, mic immediately to Send's left - the mic is
    # just an alternate way to produce the message Send then dispatches
    # (voice instead of typing), so it belongs beside Send, not beside the
    # unrelated, destructive Clear action.
    #
    # Clear conversation is a plain st.button (st.form can't contain one -
    # only form_submit_button - and _on_clear has nothing to do with the
    # form's text anyway). The visible "Send" here is NOT a second Streamlit
    # widget - it's a real HTML button rendered via components.html whose
    # onclick reaches into the parent document (same trick _AUTOSCROLL_JS
    # uses above) and clicks the real, hidden form_submit_button above, so
    # the actual send still goes through one genuine form submission either
    # way Enter or this button is used.
    #
    # voice_input() is read here (a sibling of chat_form, not inside it) and
    # acts immediately on a transcript (like a quick-action click) rather
    # than waiting for a "Send" click the way the text input does - see
    # chatbot/voice_input.py's own docstring for why a fresh transcript is
    # enqueued+rerun right here rather than via an on_click callback: custom
    # components report their value during the normal script body, not in a
    # separate callback phase the way native widgets do.
    clear_col, mic_col, send_col = st.columns([3, 1, 1])
    with clear_col:
        st.button(
            "Clear conversation",
            key="chat_clear",
            on_click=_on_clear,
            disabled=(not st.session_state.chat_history) or pending,
        )
    with mic_col:
        voice_text = voice_input(key="chat_voice", disabled=pending)
    with send_col:
        components_html(
            f"""
            <button id="send-proxy" type="button" {"disabled" if pending else ""}>Send</button>
            <style>
              html, body {{ margin: 0; padding: 0; }}
              #send-proxy {{
                width: 100%; height: 2.5rem; border-radius: 0.5rem; border: none;
                background: {settings.colors['primary']}; color: #FFFDF9;
                font-family: "Source Sans Pro", sans-serif; font-size: 1rem; font-weight: 600;
                cursor: pointer;
              }}
              #send-proxy:hover {{ filter: brightness(1.08); }}
              #send-proxy:disabled {{ opacity: 0.4; cursor: not-allowed; }}
            </style>
            <script>
              document.getElementById("send-proxy").addEventListener("click", function () {{
                var realBtn = window.parent.document.querySelector(".st-key-chat_send_hidden button");
                if (realBtn) {{ realBtn.click(); }}
              }});
            </script>
            """,
            height=40,
        )

    if voice_text and not pending:
        _enqueue(voice_text)
        st.rerun()

    # Resolving pending last, after every other element in the panel has
    # already rendered once for this run - st.rerun() halts execution
    # immediately, so anything placed *after* it (as this used to be, mid-
    # function) never runs during the "sending" pass at all. Streamlit's
    # diffing then got confused reconciling those skipped elements once
    # they reappeared on the next run, leaving the form/Clear button stuck
    # showing whatever they last rendered before the first message was ever
    # sent (chat_history looking permanently empty to them) instead of
    # picking up the real, current state.
    if pending:
        _resolve_pending()
        st.rerun()

    # Only reached when not pending (the branch above halts execution via
    # st.rerun() otherwise) - see _inject_focus_restore's own docstring for
    # why that's exactly the right moment.
    _inject_focus_restore()
    _inject_textarea_enter_to_send()
    _inject_textarea_collapsed_height_sync()


def render_chatbot() -> None:
    """Render the fixed launcher; opens an anchored panel in place. Call once per run."""
    if not settings.enable_chatbot:
        return
    with st.popover("💬 Ask the Assistant", key="chat_launcher"):
        _chat_panel()

"""Login — gates the storefront and gives the chatbot a stable user identity.

Real authentication is out of scope for this demo: any non-empty user ID /
password pair succeeds. The user ID captured here is kept in session state
and sent with every chat request so replies can be attributed to a user.
"""
from __future__ import annotations

import streamlit as st

from utils.helpers import get_logger

log = get_logger("alumni_store.login")


def _on_login() -> None:
    user_id = st.session_state.get("login_user_id", "").strip()
    password = st.session_state.get("login_password", "")
    if not user_id or not password:
        st.session_state.login_error = "Enter both a user ID and password."
        return
    st.session_state.login_error = None
    st.session_state.authenticated = True
    st.session_state.user_id = user_id
    log.info("Login ok | user_id=%s", user_id)


def render() -> None:
    st.markdown("<div style='height:10vh'></div>", unsafe_allow_html=True)
    _, mid, _ = st.columns([1, 1.1, 1])
    with mid:
        st.image("assets/logo.png", width=64)
        st.markdown("## Alumni Store sign in")
        st.caption("Demo login — any user ID / password combination works.")
        with st.form("login_form", border=True):
            st.text_input("User ID", key="login_user_id", placeholder="e.g. alum-1001")
            st.text_input("Password", key="login_password", type="password")
            st.form_submit_button(
                "Sign in", type="primary", width="stretch", on_click=_on_login
            )
        if st.session_state.get("login_error"):
            st.error(st.session_state.login_error)

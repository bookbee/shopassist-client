"""Login — gates the storefront and gives the chatbot a stable user identity.

Real authentication is out of scope for this demo: the "password" must
simply match the user ID entered alongside it (see _on_login() below) -
enough to demonstrate both a happy path (matching values) and an error
path (mismatched values) without a real credentials store. The user ID
captured here is kept in session state
and sent with every chat request so replies can be attributed to a user.
It's also mirrored into the ?user_id= URL query param, so a browser
refresh (which otherwise starts a brand-new, empty session_state) still
resolves back to the same user - see utils.helpers.init_state(), which
restores from that param, and pages/profile.py's "Log out" button, which
clears it.
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
    # Demo credential check: password must equal the user ID - gives this
    # login screen a real happy path (matching values) and error path
    # (mismatched values) without standing up an actual credentials store.
    if password != user_id:
        st.session_state.login_error = "Incorrect credentials. Please check your User ID or password and try again."
        return
    st.session_state.login_error = None
    st.session_state.authenticated = True
    st.session_state.user_id = user_id
    st.query_params["user_id"] = user_id
    log.info("Login ok | user_id=%s", user_id)


def render() -> None:
    st.markdown("<div style='height:10vh'></div>", unsafe_allow_html=True)
    _, mid, _ = st.columns([1, 1.1, 1])
    with mid:
        st.image("assets/logo.png", width=64)
        st.markdown("## Alumni Store sign in")
        st.caption("Demo login — enter your User ID as the password too.")
        # The seeded customers are alum-1001 .. alum-1010
        # (shopassist-database/postgres/seeds/seed_customers.sql). Spelled
        # out here because any *other* ID logs in fine but then has no
        # orders or history behind it, which reads as a broken chatbot
        # rather than an empty account.
        st.caption("Try **alum-1001** (password `alum-1001`). Seeded demo customers are `alum-1001` … `alum-1010`.")
        with st.form("login_form", border=True):
            st.text_input("User ID", key="login_user_id", placeholder="e.g. alum-1001")
            st.text_input("Password", key="login_password", type="password")
            st.form_submit_button(
                "Sign in", type="primary", width="stretch", on_click=_on_login
            )
        if st.session_state.get("login_error"):
            st.error(st.session_state.login_error)

"""IISc Alumni Store — entrypoint.

A capstone demonstration of an AI-enabled alumni merchandise portal.
Everything (catalog, cart, checkout, orders, profile) is mocked from JSON
files; the floating chatbot is the only component that calls a real,
remote API Gateway (configured in config.yaml / .env).

Run with:
    streamlit run app.py
"""
from __future__ import annotations

import base64
from functools import lru_cache
from pathlib import Path

import streamlit as st

from chatbot.chat_ui import render_chatbot
from components.footer import render_footer
from components.navbar import render_navbar
from config import settings
from pages import about, cart, catalog, checkout, home, login, orders, product, profile
from utils.helpers import get_logger, init_state

log = get_logger()

ROUTES = {
    "home": home.render,
    "catalog": catalog.render,
    "product": product.render,
    "cart": cart.render,
    "checkout": checkout.render,
    "orders": orders.render,
    "profile": profile.render,
    "about": about.render,
}


@lru_cache(maxsize=1)
def _brand_logo_data_uri() -> str | None:
    """Small logo, base64-inlined so styles.css can use it as a CSS
    background (chat header badge + chat panel watermark) without relying
    on Streamlit's static file serving. Uses the pre-shrunk 160x160 copy —
    plenty sharp at the small sizes it's actually displayed at, a fraction
    of the full asset's size to re-send on every rerun.
    """
    logo_path = Path(__file__).parent / "assets" / "logo_small.png"
    try:
        encoded = base64.b64encode(logo_path.read_bytes()).decode("ascii")
    except OSError as exc:
        log.warning("Could not load brand logo: %s", exc)
        return None
    return f"data:image/png;base64,{encoded}"


def load_css() -> None:
    css_path = Path(__file__).parent / "styles" / "styles.css"
    logo_uri = _brand_logo_data_uri()
    if logo_uri:
        st.markdown(
            f"<style>:root {{ --brand-logo: url('{logo_uri}'); }}</style>",
            unsafe_allow_html=True,
        )
    try:
        st.markdown(f"<style>{css_path.read_text(encoding='utf-8')}</style>",
                    unsafe_allow_html=True)
    except OSError as exc:
        log.warning("Could not load stylesheet: %s", exc)


def main() -> None:
    st.set_page_config(
        page_title=settings.app_title,
        page_icon="🎓",
        layout="wide",
        initial_sidebar_state="collapsed",
    )
    init_state()
    load_css()

    if not st.session_state.authenticated:
        login.render()
        return

    render_navbar()

    page = st.session_state.page
    render = ROUTES.get(page)
    if render is None:
        log.error("Unknown route '%s', falling back to home", page)
        st.session_state.page = "home"
        render = home.render

    try:
        render()
    except Exception:  # noqa: BLE001 — last-resort guard so the demo never dies
        log.exception("Unhandled error rendering page '%s'", page)
        st.error("Something went wrong rendering this page. Please try again.")

    render_footer()
    render_chatbot()


if __name__ == "__main__":
    main()

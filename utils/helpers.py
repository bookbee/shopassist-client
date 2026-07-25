"""Shared helpers: logging, data access, session state, cart math, navigation."""
from __future__ import annotations

import json
import logging
import random
import string
from datetime import date, timedelta
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any
from uuid import uuid4

import streamlit as st

from config import settings
from utils.constants import (
    CURRENCY,
    DELIVERY_DAYS_ESTIMATE,
    FREE_SHIPPING_THRESHOLD,
    GST_RATE,
    SHIPPING_FLAT_FEE,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
LOG_DIR = PROJECT_ROOT / "logs"


# --------------------------------------------------------------------------- #
# Logging
# --------------------------------------------------------------------------- #
def get_logger(name: str = "alumni_store") -> logging.Logger:
    """Return an app logger writing INFO+ to logs/app.log (rotating).

    Every call site names its own child logger (e.g. "alumni_store.chat")
    so %(name)s identifies the module in app.log. Each gets its own handler
    below, so propagate is disabled — otherwise a record would also bubble
    up to the parent "alumni_store" logger's handler and get written twice.
    """
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger
    logger.setLevel(getattr(logging, settings.log_level, logging.INFO))
    logger.propagate = False
    LOG_DIR.mkdir(exist_ok=True)
    handler = RotatingFileHandler(
        LOG_DIR / "app.log", maxBytes=512_000, backupCount=3, encoding="utf-8"
    )
    handler.setFormatter(
        logging.Formatter("%(asctime)s | %(levelname)-7s | %(name)s | %(message)s")
    )
    logger.addHandler(handler)
    return logger


log = get_logger()


# --------------------------------------------------------------------------- #
# Data access (mock JSON files stand in for a real backend)
# --------------------------------------------------------------------------- #
@st.cache_data(show_spinner=False)
def load_json(filename: str) -> Any:
    """Load a JSON file from data/ with friendly failure."""
    path = DATA_DIR / filename
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except FileNotFoundError:
        log.error("Data file missing: %s", path)
        return []
    except json.JSONDecodeError as exc:
        log.error("Malformed JSON in %s: %s", path, exc)
        return []


def get_products() -> list[dict]:
    return load_json("products.json")


def get_product(product_id: str) -> dict | None:
    return next((p for p in get_products() if p["id"] == product_id), None)


def get_orders() -> list[dict]:
    return load_json("orders.json")


def get_order(order_id: str) -> dict | None:
    return next((o for o in get_orders() if o["order_id"] == order_id), None)


def get_profile() -> dict:
    return load_json("profile.json") or {}


def get_faq() -> list[dict]:
    return load_json("faq.json")


def get_announcements() -> list[dict]:
    return load_json("announcements.json")


# --------------------------------------------------------------------------- #
# Session state
# --------------------------------------------------------------------------- #
def init_state() -> None:
    """Idempotently seed everything the app keeps in Streamlit session state."""
    defaults: dict[str, Any] = {
        "page": "home",                  # current router target
        "cart": {},                      # {product_id: qty}
        "authenticated": False,          # gates the app behind pages/login.py
        "user_id": None,                 # identity captured at login; sent with chat requests
        "profile": get_profile(),
        "chat_history": [],              # [{role, content, meta}]
        "chat_session_id": str(uuid4()),
        "chat_pending": None,            # user message awaiting a gateway reply, or None
        "selected_product": None,        # product_id for detail page
        "checkout": {"step": "form", "order_id": None, "eta": None},
        "recently_viewed": [],           # [product_id]
        "last_ticket": None,             # escalation ticket dict
        "wishlist": set(),
    }
    for key, value in defaults.items():
        st.session_state.setdefault(key, value)


def go_to(page: str) -> None:
    """Route to a page on the next rerun."""
    st.session_state.page = page
    log.info("Navigate -> %s", page)


def get_device_type() -> str:
    """Classify the caller's device from the User-Agent header.

    Not sent to the chat gateway — its ChatRequest schema has no device
    field, only source_channel (web_chat/mobile_app/twitter). Kept as a
    general-purpose helper for any future device-aware UI.
    """
    try:
        user_agent = (st.context.headers.get("User-Agent") or "").lower()
    except Exception:  # noqa: BLE001 — headers can be unavailable outside a live session
        user_agent = ""
    if "ipad" in user_agent or "tablet" in user_agent:
        return "tablet"
    if any(token in user_agent for token in ("mobi", "iphone", "android")):
        return "mobile"
    return "desktop"


def view_product(product_id: str) -> None:
    st.session_state.selected_product = product_id
    recent: list[str] = st.session_state.recently_viewed
    if product_id in recent:
        recent.remove(product_id)
    recent.insert(0, product_id)
    del recent[6:]
    go_to("product")


# --------------------------------------------------------------------------- #
# Cart
# --------------------------------------------------------------------------- #
def add_to_cart(product_id: str, qty: int = 1) -> None:
    cart: dict[str, int] = st.session_state.cart
    cart[product_id] = cart.get(product_id, 0) + qty
    st.session_state[f"flash_{product_id}"] = qty  # one-shot UI confirmation
    log.info("Cart add: %s x%s", product_id, qty)
    st.toast(f"Added to cart — {qty} item(s)", icon="🛒")


def set_cart_qty(product_id: str, qty: int) -> None:
    cart: dict[str, int] = st.session_state.cart
    if qty <= 0:
        cart.pop(product_id, None)
    else:
        cart[product_id] = qty


def remove_from_cart(product_id: str) -> None:
    st.session_state.cart.pop(product_id, None)
    st.toast("Removed from cart", icon="🗑️")


def cart_items() -> list[dict]:
    """Cart lines joined with product data."""
    lines = []
    for pid, qty in st.session_state.cart.items():
        product = get_product(pid)
        if product:
            lines.append({"product": product, "qty": qty, "line_total": product["price"] * qty})
    return lines


def cart_count() -> int:
    return sum(st.session_state.cart.values())


def cart_totals() -> dict[str, float]:
    subtotal = sum(line["line_total"] for line in cart_items())
    gst = round(subtotal * GST_RATE, 2)
    shipping = 0 if (subtotal >= FREE_SHIPPING_THRESHOLD or subtotal == 0) else SHIPPING_FLAT_FEE
    return {
        "subtotal": subtotal,
        "gst": gst,
        "shipping": shipping,
        "total": round(subtotal + gst + shipping, 2),
    }


# --------------------------------------------------------------------------- #
# Formatting & order helpers
# --------------------------------------------------------------------------- #
def inr(amount: float) -> str:
    """Format a number as Indian rupees, e.g. ₹1,499."""
    if amount == int(amount):
        return f"{CURRENCY}{int(amount):,}"
    return f"{CURRENCY}{amount:,.2f}"


def stars(rating: float) -> str:
    full = int(rating)
    half = "½" if rating - full >= 0.5 else ""
    return "★" * full + half


def generate_order_id() -> str:
    return "ord-" + "".join(random.choices(string.digits, k=4))


def estimated_delivery() -> str:
    return (date.today() + timedelta(days=DELIVERY_DAYS_ESTIMATE)).strftime("%A, %d %B %Y")

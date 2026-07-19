"""Reusable product card used on Home and Catalog pages."""
from __future__ import annotations

import streamlit as st

from utils.helpers import add_to_cart, inr, stars, view_product


def _stock_badge(stock: int) -> str:
    if stock == 0:
        return "<span class='badge badge-out'>Out of stock</span>"
    if stock <= 20:
        return f"<span class='badge badge-low'>Only {stock} left</span>"
    return "<span class='badge badge-stock'>In stock</span>"


def render_product_card(product: dict, key_prefix: str = "card") -> None:
    """A bordered card: image, name, blurb, price, rating, stock, actions.

    Keyed so styles.css can target this specific card (not every bordered
    container app-wide) to equalize height across a row and pin the
    View/Add-to-Cart buttons to the bottom - product name/description length
    varies per item, and without a shared height + bottom-anchored action
    row, cards in the same row end up visibly different heights.
    """
    with st.container(border=True, key=f"prodcard_{key_prefix}_{product['id']}"):
        with st.container(key=f"prodimg_{key_prefix}_{product['id']}"):
            st.image(product["image"], width="stretch")
        st.markdown(
            f"<span class='badge badge-cat'>{product['category']}</span>",
            unsafe_allow_html=True,
        )
        st.markdown(f"**{product['name']}**")
        st.markdown(
            f"<span class='muted'>{product['short_description']}</span>",
            unsafe_allow_html=True,
        )
        st.markdown(
            f"<span class='price'>{inr(product['price'])}</span> &nbsp; "
            f"<span class='rating'>{stars(product['rating'])}</span> "
            f"<span class='muted'>{product['rating']} ({product['reviews_count']})</span><br>"
            f"{_stock_badge(product['stock'])}",
            unsafe_allow_html=True,
        )

        view_col, add_col = st.columns(2)
        if view_col.button("View", key=f"{key_prefix}_view_{product['id']}",
                           width="stretch"):
            view_product(product["id"])
            st.rerun()
        if add_col.button(
            "Add to Cart",
            key=f"{key_prefix}_add_{product['id']}",
            type="primary",
            width="stretch",
            disabled=product["stock"] == 0,
        ):
            add_to_cart(product["id"])
            st.rerun()

        # one-shot confirmation flash (set by add_to_cart, cleared after render)
        flashed = st.session_state.pop(f"flash_{product['id']}", None)
        if flashed:
            st.markdown(
                f"<div class='cart-flash'>✓ Added to cart ({flashed})</div>",
                unsafe_allow_html=True,
            )

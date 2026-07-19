"""Product details — large image, specs, reviews, quantity selector."""
from __future__ import annotations

import streamlit as st

from components.product_card import render_product_card
from utils.helpers import add_to_cart, get_product, get_products, go_to, inr, stars


def render() -> None:
    product = get_product(st.session_state.selected_product or "")
    if product is None:
        st.warning("Product not found.")
        if st.button("Back to Catalog"):
            go_to("catalog")
            st.rerun()
        return

    if st.button("← Continue Shopping"):
        go_to("catalog")
        st.rerun()

    img_col, info_col = st.columns([1.1, 1.4], gap="large")

    with img_col:
        with st.container(key=f"prodimg_detail_{product['id']}"):
            st.image(product["image"], width="stretch")

    with info_col:
        st.markdown(f"# {product['name']}")
        st.markdown("<div class='crest-rule'></div>", unsafe_allow_html=True)
        st.markdown(
            f"<span class='badge badge-cat'>{product['category']}</span> &nbsp;"
            f"<span class='rating'>{stars(product['rating'])}</span> "
            f"<span class='muted'>{product['rating']} · {product['reviews_count']} reviews</span>",
            unsafe_allow_html=True,
        )
        st.markdown(f"<div class='price' style='font-size:2rem'>{inr(product['price'])}</div>",
                    unsafe_allow_html=True)
        st.caption("Inclusive of all taxes · free shipping above ₹999")
        st.write(product["description"])

        in_stock = product["stock"] > 0
        if in_stock:
            qty = st.number_input(
                "Quantity", min_value=1, max_value=min(10, product["stock"]), value=1
            )
            if st.button("Add to Cart", type="primary", width="stretch"):
                add_to_cart(product["id"], int(qty))
                st.rerun()
            flashed = st.session_state.pop(f"flash_{product['id']}", None)
            if flashed:
                st.markdown(
                    f"<div class='cart-flash'>✓ Added {flashed} to cart — "
                    "see the Cart tab above</div>",
                    unsafe_allow_html=True,
                )
        else:
            st.error("Out of stock — join the waitlist and we'll email you on restock.")
            if st.button("Join waitlist", width="stretch"):
                st.toast("You're on the waitlist!", icon="📬")

    # ---- specifications ----
    st.markdown("## Specifications")
    st.markdown("<div class='crest-rule'></div>", unsafe_allow_html=True)
    with st.container(border=True):
        for label, value in product["specs"].items():
            st.markdown(
                f"<div style='display:flex;justify-content:space-between'>"
                f"<span class='muted'>{label}</span><span>{value}</span></div>",
                unsafe_allow_html=True,
            )

    # ---- reviews ----
    st.markdown("## Reviews")
    st.markdown("<div class='crest-rule'></div>", unsafe_allow_html=True)
    for review in product["reviews"]:
        with st.container(border=True):
            st.markdown(
                f"**{review['user']}** &nbsp; "
                f"<span class='rating'>{stars(review['rating'])}</span>",
                unsafe_allow_html=True,
            )
            st.write(review["comment"])

    # ---- recently viewed ----
    recent_ids = [
        pid for pid in st.session_state.recently_viewed if pid != product["id"]
    ][:4]
    if recent_ids:
        st.markdown("## Recently viewed")
        st.markdown("<div class='crest-rule'></div>", unsafe_allow_html=True)
        recent = [p for p in get_products() if p["id"] in recent_ids]
        for col, item in zip(st.columns(4), recent):
            with col:
                render_product_card(item, key_prefix="recent")

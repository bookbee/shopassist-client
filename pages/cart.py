"""Shopping Cart — line items with quantity controls and order summary."""
from __future__ import annotations

import streamlit as st

from components.cart_widget import render_cart_summary
from utils.helpers import cart_items, go_to, inr, remove_from_cart, set_cart_qty


def render() -> None:
    st.markdown("# Shopping Cart")
    st.markdown("<div class='crest-rule'></div>", unsafe_allow_html=True)

    lines = cart_items()
    if not lines:
        st.info("Your cart is empty. The catalog is one click away.")
        if st.button("Continue Shopping", type="primary"):
            go_to("catalog")
            st.rerun()
        return

    items_col, summary_col = st.columns([2.2, 1], gap="large")

    with items_col:
        for line in lines:
            product, qty = line["product"], line["qty"]
            with st.container(border=True):
                img, info, controls = st.columns([0.9, 2.2, 1.3])
                with img:
                    with st.container(key=f"prodimg_cart_{product['id']}"):
                        st.image(product["image"], width="stretch")
                with info:
                    st.markdown(f"**{product['name']}**")
                    st.markdown(
                        f"<span class='muted'>{inr(product['price'])} each</span>",
                        unsafe_allow_html=True,
                    )
                    st.markdown(
                        f"<span class='price'>{inr(line['line_total'])}</span>",
                        unsafe_allow_html=True,
                    )
                with controls:
                    new_qty = st.number_input(
                        "Qty",
                        min_value=1,
                        max_value=10,
                        value=qty,
                        key=f"qty_{product['id']}",
                    )
                    if new_qty != qty:
                        set_cart_qty(product["id"], int(new_qty))
                        st.rerun()
                    if st.button(
                        "Remove", key=f"rm_{product['id']}", width="stretch"
                    ):
                        remove_from_cart(product["id"])
                        st.rerun()

    with summary_col:
        render_cart_summary()
        if st.button("Checkout →", type="primary", width="stretch"):
            st.session_state.checkout = {"step": "form", "order_id": None, "eta": None}
            go_to("checkout")
            st.rerun()
        if st.button("Continue Shopping", width="stretch"):
            go_to("catalog")
            st.rerun()

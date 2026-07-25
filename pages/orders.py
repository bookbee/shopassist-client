"""Order History — six mocked past orders with tracking and invoices."""
from __future__ import annotations

import streamlit as st

from utils.helpers import get_orders, inr


def _invoice_text(order: dict) -> str:
    lines = [
        "IISc ALUMNI STORE — TAX INVOICE (DEMO)",
        "Indian Institute of Science, Bengaluru 560012",
        "-" * 46,
        f"Order:  {order['order_id']}",
        f"Date:   {order['date']}",
        f"Status: {order['status']}",
        "-" * 46,
    ]
    for item in order["items"]:
        lines.append(f"{item['name']}  x{item['qty']}  {inr(item['price'] * item['qty'])}")
    lines += ["-" * 46, f"TOTAL (incl. GST): {inr(order['amount'])}"]
    return "\n".join(lines)


def _render_timeline(order: dict) -> None:
    for step in order["timeline"]:
        dot = "●" if step["done"] else "○"
        cls = "" if step["done"] else " pending"
        st.markdown(
            f"<div class='tl-step'><span class='tl-dot{cls}'>{dot}</span>"
            f"<span><strong>{step['step']}</strong> "
            f"<span class='muted'>— {step['date']}</span></span></div>",
            unsafe_allow_html=True,
        )


def render() -> None:
    st.markdown("# Order History")
    st.markdown("<div class='crest-rule'></div>", unsafe_allow_html=True)
    st.caption("Tip: ask the assistant “Where is order ord-1001?” to track by chat.")

    for order in get_orders():
        with st.container(border=True):
            head_l, head_r = st.columns([3, 1])
            with head_l:
                st.markdown(f"**Order `{order['order_id']}`**")
                st.markdown(
                    f"<span class='muted'>Placed {order['date']} · "
                    f"{len(order['items'])} item(s)</span>",
                    unsafe_allow_html=True,
                )
            with head_r:
                st.markdown(
                    f"<div style='text-align:right'>"
                    f"<span class='price'>{inr(order['amount'])}</span><br>"
                    f"<span class='badge badge-status'>{order['status']}</span></div>",
                    unsafe_allow_html=True,
                )

            for item in order["items"]:
                st.markdown(
                    f"<span class='muted'>· {item['name']} × {item['qty']}</span>",
                    unsafe_allow_html=True,
                )

            action_track, action_invoice, _ = st.columns([1, 1, 2])
            with action_track:
                with st.popover("Track Order", width="stretch"):
                    st.markdown(f"**Tracking `{order['order_id']}`**")
                    _render_timeline(order)
                    st.caption(f"Estimated / actual delivery: {order['eta']}")
            with action_invoice:
                st.download_button(
                    "Invoice",
                    data=_invoice_text(order),
                    file_name=f"invoice_{order['order_id']}.txt",
                    mime="text/plain",
                    key=f"inv_{order['order_id']}",
                    width="stretch",
                )

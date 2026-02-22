import streamlit as st
from datetime import datetime, timezone
import sys
import os
import io
import qrcode

sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from utils.supabase_client import get_client


def make_qr(code: str) -> bytes:
    qr = qrcode.QRCode(box_size=8, border=2)
    qr.add_data(code)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()

st.set_page_config(page_title="My Points — Kinik Thai", layout="centered")
st.title("My Points")
st.markdown("---")

sb = get_client()


def get_customer_by_phone(phone: str):
    res = sb.table("customers").select("*").eq("phone", phone).execute()
    return res.data[0] if res.data else None


def get_active_balance(customer_id: str) -> int:
    res = (
        sb.table("point_lots")
        .select("points_remaining")
        .eq("customer_id", customer_id)
        .eq("status", "ACTIVE")
        .execute()
    )
    return sum(row["points_remaining"] for row in res.data)


def get_active_coupons(customer_id: str):
    now_iso = datetime.now(timezone.utc).isoformat()
    res = (
        sb.table("coupons")
        .select("code, value_thb, expires_at, created_at")
        .eq("customer_id", customer_id)
        .eq("status", "ACTIVE")
        .gt("expires_at", now_iso)
        .order("expires_at", desc=False)
        .execute()
    )
    return res.data


# ------------------------------------------------------------------
# Phone lookup
# ------------------------------------------------------------------

phone = st.text_input("Enter your phone number")

if st.button("Check My Points"):
    if not phone.strip():
        st.warning("Please enter your phone number.")
    else:
        customer = get_customer_by_phone(phone.strip())
        if customer is None:
            st.error("Phone number not found. Please contact the store.")
        else:
            st.session_state["cust_customer"] = customer
            st.session_state["cust_balance"] = get_active_balance(customer["customer_id"])
            st.session_state["cust_coupons"] = get_active_coupons(customer["customer_id"])

if "cust_customer" in st.session_state:
    customer = st.session_state["cust_customer"]
    balance = st.session_state["cust_balance"]
    coupons = st.session_state["cust_coupons"]

    st.markdown(f"### Welcome, {customer['name']}")
    st.markdown("---")

    # Points summary
    col1, col2 = st.columns(2)
    with col1:
        st.metric("Active Points", f"{balance:,}")
    with col2:
        if balance >= 1000:
            st.metric("Redeemable Coupons", f"{balance // 1000}")
        else:
            needed = 1000 - balance
            st.metric("Points to Next Coupon", f"{needed:,}")

    # Redeem button
    if balance >= 1000:
        st.markdown("---")
        if st.button("Redeem 1,000 pts → 50 THB Coupon"):
            try:
                rpc_res = sb.rpc(
                    "redeem_fifo", {"p_customer_id": customer["customer_id"]}
                ).execute()
                coupon_code = rpc_res.data
                st.success(f"Coupon issued: **{coupon_code}** (50 THB, valid 1 year)")
                # Refresh
                st.session_state["cust_balance"] = get_active_balance(
                    customer["customer_id"]
                )
                st.session_state["cust_coupons"] = get_active_coupons(
                    customer["customer_id"]
                )
                st.experimental_rerun()
            except Exception as ex:
                st.error(f"Redemption failed: {ex}")

    # Active coupons
    st.markdown("---")
    st.subheader("Active Coupons")
    if not coupons:
        st.info("No active coupons.")
    else:
        st.caption("Show the QR code to the cashier.")
        for c in coupons:
            expires = datetime.fromisoformat(
                c["expires_at"].replace("Z", "+00:00")
            ).strftime("%d %b %Y")

            col_qr, col_info = st.columns([1, 2])
            with col_qr:
                st.image(make_qr(c["code"]), width=160)
            with col_info:
                st.markdown(f"## {c['code']}")
                st.markdown(f"**Value:** {int(c['value_thb'])} THB")
                st.markdown(f"**Expires:** {expires}")
            st.markdown("---")

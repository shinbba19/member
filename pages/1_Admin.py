import streamlit as st
from datetime import date, datetime, timezone
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from utils.supabase_client import get_client

st.set_page_config(page_title="Admin — Kinik Thai", layout="centered")
st.title("Admin Portal")
st.markdown("---")

sb = get_client()


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

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


# ------------------------------------------------------------------
# Tabs
# ------------------------------------------------------------------

tab1, tab2, tab3, tab4 = st.tabs(
    ["Add Invoice", "Redeem Points", "Use Coupon", "Run Expiry Job"]
)


# ══════════════════════════════════════════════════════════════════
# TAB 1 – Add Invoice
# ══════════════════════════════════════════════════════════════════
with tab1:
    st.subheader("Add Invoice")

    with st.form("add_invoice_form"):
        phone = st.text_input("Customer Phone *")
        name = st.text_input("Customer Name (required for new customer)")
        invoice_no = st.text_input("Invoice No *")
        amount = st.number_input("Amount (THB) *", min_value=0.0, step=10.0, format="%.2f")
        invoice_date = st.date_input("Invoice Date *", value=date.today())
        created_by = st.text_input("Created By *")
        submitted = st.form_submit_button("Submit Invoice")

    if submitted:
        # Basic validation
        errors = []
        if not phone.strip():
            errors.append("Phone is required.")
        if not invoice_no.strip():
            errors.append("Invoice No is required.")
        if not created_by.strip():
            errors.append("Created By is required.")
        if amount <= 0:
            errors.append("Amount must be greater than 0.")

        if errors:
            for e in errors:
                st.error(e)
        else:
            try:
                # Upsert customer
                customer = get_customer_by_phone(phone.strip())
                if customer is None:
                    if not name.strip():
                        st.error("Customer not found. Please provide a name to register.")
                        st.stop()
                    res = (
                        sb.table("customers")
                        .insert({"name": name.strip(), "phone": phone.strip()})
                        .execute()
                    )
                    customer = res.data[0]
                    st.info(f"New customer registered: {customer['name']}")

                customer_id = customer["customer_id"]

                # Check invoice_no uniqueness
                existing = (
                    sb.table("invoices")
                    .select("invoice_no")
                    .eq("invoice_no", invoice_no.strip())
                    .execute()
                )
                if existing.data:
                    st.error(f"Invoice No '{invoice_no.strip()}' already exists.")
                    st.stop()

                # Insert invoice
                sb.table("invoices").insert(
                    {
                        "invoice_no": invoice_no.strip(),
                        "customer_id": customer_id,
                        "amount": float(amount),
                        "invoice_date": invoice_date.isoformat(),
                        "created_by": created_by.strip(),
                        "status": "APPROVED",
                    }
                ).execute()

                # Call RPC to create lot
                rpc_res = sb.rpc(
                    "create_lot_for_invoice", {"p_invoice_no": invoice_no.strip()}
                ).execute()

                points_earned = int(amount // 10)
                new_balance = get_active_balance(customer_id)

                st.success(
                    f"Invoice added. +{points_earned} pts earned. "
                    f"Balance: {new_balance} pts"
                )

            except Exception as ex:
                st.error(f"Error: {ex}")


# ══════════════════════════════════════════════════════════════════
# TAB 2 – Redeem Points
# ══════════════════════════════════════════════════════════════════
with tab2:
    st.subheader("Redeem Points")

    phone_r = st.text_input("Customer Phone", key="redeem_phone")

    if st.button("Look Up", key="lookup_redeem"):
        if not phone_r.strip():
            st.warning("Enter a phone number.")
        else:
            customer = get_customer_by_phone(phone_r.strip())
            if customer is None:
                st.error("Customer not found.")
            else:
                st.session_state["redeem_customer"] = customer
                balance = get_active_balance(customer["customer_id"])
                st.session_state["redeem_balance"] = balance

    if "redeem_customer" in st.session_state:
        customer = st.session_state["redeem_customer"]
        balance = st.session_state["redeem_balance"]

        st.write(f"**Customer:** {customer['name']}")
        st.write(f"**Active Points:** {balance}")

        if balance >= 1000:
            if st.button("Redeem 1,000 pts → 50 THB Coupon"):
                try:
                    rpc_res = sb.rpc(
                        "redeem_fifo", {"p_customer_id": customer["customer_id"]}
                    ).execute()
                    coupon_code = rpc_res.data
                    new_balance = get_active_balance(customer["customer_id"])
                    st.session_state["redeem_balance"] = new_balance
                    st.success(f"Coupon issued: **{coupon_code}**")
                    st.info(f"Remaining balance: {new_balance} pts")
                    del st.session_state["redeem_customer"]
                except Exception as ex:
                    st.error(f"Redemption failed: {ex}")
        else:
            deficit = 1000 - balance
            st.warning(f"Insufficient points. Need {deficit} more pts to redeem.")


# ══════════════════════════════════════════════════════════════════
# TAB 3 – Use Coupon
# ══════════════════════════════════════════════════════════════════
with tab3:
    st.subheader("Use Coupon")

    def mark_coupon_used(coupon_id: str, code: str, value: float):
        try:
            sb.table("coupons").update(
                {
                    "status": "USED",
                    "used_at": datetime.now(timezone.utc).isoformat(),
                }
            ).eq("coupon_id", coupon_id).execute()
            st.success(f"Coupon **{code}** used — {int(value)} THB discount applied.")
            if "use_coupons" in st.session_state:
                del st.session_state["use_coupons"]
                del st.session_state["use_customer"]
        except Exception as ex:
            st.error(f"Error: {ex}")

    # ── Phone lookup (primary cashier flow) ──
    phone_u = st.text_input("Customer Phone", key="use_phone")

    if st.button("Look Up Customer", key="lookup_use"):
        if not phone_u.strip():
            st.warning("Enter a phone number.")
        else:
            customer = get_customer_by_phone(phone_u.strip())
            if customer is None:
                st.error("Customer not found.")
            else:
                now_iso = datetime.now(timezone.utc).isoformat()
                res = (
                    sb.table("coupons")
                    .select("*")
                    .eq("customer_id", customer["customer_id"])
                    .eq("status", "ACTIVE")
                    .gt("expires_at", now_iso)
                    .order("expires_at", desc=False)
                    .execute()
                )
                st.session_state["use_customer"] = customer
                st.session_state["use_coupons"] = res.data

    if "use_customer" in st.session_state:
        customer = st.session_state["use_customer"]
        coupons_list = st.session_state.get("use_coupons", [])

        st.write(f"**Customer:** {customer['name']}")

        if not coupons_list:
            st.info("No active coupons for this customer.")
        else:
            st.write(f"**Active coupons: {len(coupons_list)}**")
            st.markdown("---")
            for c in coupons_list:
                expires = datetime.fromisoformat(
                    c["expires_at"].replace("Z", "+00:00")
                ).strftime("%d %b %Y")
                col_code, col_val, col_exp, col_btn = st.columns([3, 1, 2, 2])
                col_code.markdown(f"`{c['code']}`")
                col_val.markdown(f"**{int(c['value_thb'])} THB**")
                col_exp.markdown(f"Exp: {expires}")
                if col_btn.button("Use", key=f"use_{c['coupon_id']}"):
                    mark_coupon_used(c["coupon_id"], c["code"], c["value_thb"])

    # ── Manual code entry (fallback) ──
    st.markdown("---")
    st.caption("Or enter coupon code manually:")
    coupon_code = st.text_input("Coupon Code", key="use_coupon_code")

    if st.button("Validate & Use Coupon"):
        if not coupon_code.strip():
            st.warning("Enter a coupon code.")
        else:
            try:
                res = (
                    sb.table("coupons")
                    .select("*")
                    .eq("code", coupon_code.strip().upper())
                    .execute()
                )

                if not res.data:
                    st.error("Coupon code not found.")
                else:
                    coupon = res.data[0]

                    if coupon["status"] != "ACTIVE":
                        st.error(
                            f"Coupon is not active (status: {coupon['status']})."
                        )
                    else:
                        expires_at = datetime.fromisoformat(
                            coupon["expires_at"].replace("Z", "+00:00")
                        )
                        if expires_at < datetime.now(timezone.utc):
                            sb.table("coupons").update({"status": "EXPIRED"}).eq(
                                "coupon_id", coupon["coupon_id"]
                            ).execute()
                            st.error("Coupon has expired.")
                        else:
                            mark_coupon_used(
                                coupon["coupon_id"], coupon["code"], coupon["value_thb"]
                            )

            except Exception as ex:
                st.error(f"Error: {ex}")


# ══════════════════════════════════════════════════════════════════
# TAB 4 – Run Expiry Job
# ══════════════════════════════════════════════════════════════════
with tab4:
    st.subheader("Run Expiry Job")
    st.caption(
        "Marks all point lots past their expiry date as EXPIRED. "
        "Safe to run at any time."
    )

    if st.button("Run expire_lots()"):
        try:
            res = sb.rpc("expire_lots", {}).execute()
            count = res.data if res.data is not None else 0
            st.success(f"Done. {count} lot(s) expired.")
        except Exception as ex:
            st.error(f"Error: {ex}")

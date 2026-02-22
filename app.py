import streamlit as st

st.set_page_config(
    page_title="Kinik Thai Loyalty",
    page_icon="K",
    layout="centered",
)

st.title("Kinik Thai Loyalty Point System")
st.markdown("---")

col1, col2 = st.columns(2)

with col1:
    st.subheader("Admin Portal")
    st.markdown(
        "Manage invoices, redeem points, validate coupons, and run the expiry job."
    )
    st.markdown("Use the **Admin** link in the sidebar.")

with col2:
    st.subheader("Customer Portal")
    st.markdown(
        "Check your point balance and active coupons using your phone number."
    )
    st.markdown("Use the **Customer** link in the sidebar.")

st.markdown("---")
st.caption("Kinik Thai Co., Ltd. — Internal Use Only")

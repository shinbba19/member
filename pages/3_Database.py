import streamlit as st
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from utils.supabase_client import get_client

st.set_page_config(page_title="Database — Kinik Thai", layout="wide")
st.title("Database Viewer")
st.markdown("---")

sb = get_client()

# table_key -> sort column (None = no ordering)
TABLES = {
    "customers":          ("Customers",          "created_at"),
    "invoices":           ("Invoices",            "created_at"),
    "point_lots":         ("Point Lots",          "earned_at"),
    "coupons":            ("Coupons",             "created_at"),
    "redeems":            ("Redeems",             "created_at"),
    "redeem_allocations": ("Redeem Allocations",  "created_at"),
}

for table_key, (table_label, sort_col) in TABLES.items():
    with st.expander(table_label, expanded=False):
        try:
            res = sb.table(table_key).select("*").order(sort_col, desc=True).execute()
            data = res.data
            if data:
                st.dataframe(data)
                st.caption(f"{len(data)} row(s)")
            else:
                st.info("No records.")
        except Exception as ex:
            st.error(f"Error loading {table_label}: {ex}")

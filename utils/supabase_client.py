import os
import streamlit as st
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

_client: Client = None


def get_client() -> Client:
    global _client
    if _client is None:
        url = os.environ.get("SUPABASE_URL")
        key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
        if not url or not key:
            st.error("Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY in environment.")
            st.stop()
        _client = create_client(url, key)
    return _client

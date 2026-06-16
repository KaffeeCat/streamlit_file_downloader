import streamlit as st

from download_route import build_download_routes

app = st.App(
    "ui.py",
    routes=build_download_routes(),
)

"""Run with: python -m streamlit run streamlit_app.py."""
from pathlib import Path
import streamlit as st
from starlette.routing import WebSocketRoute
from zentromart.live_voice import voice_socket

app = st.App(Path(__file__).with_name("chat_app.py"), routes=[WebSocketRoute("/api/voice", voice_socket)])

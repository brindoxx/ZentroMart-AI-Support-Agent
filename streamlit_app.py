"""Run with: python -m streamlit run streamlit_app.py."""
from pathlib import Path
from contextlib import asynccontextmanager
import asyncio
import streamlit as st
from starlette.routing import WebSocketRoute
from zentromart.live_voice import voice_socket

@asynccontextmanager
async def lifespan(app):
    # The Streamlit runtime exists here, so startup and UI use the same caches.
    from zentromart.ui_resources import warm_startup
    print('Preparing public knowledge, document search and local model...', flush=True)
    try:
        await asyncio.to_thread(warm_startup)
    except Exception:
        raise RuntimeError('Public resource startup failed. Check dataset paths, dependencies and embedding cache; no provider request was made.') from None
    print('ZentroMart ready: public resources warmed; no Gemini/Gnani request made.', flush=True)
    yield {'resources_ready': True}


app = st.App(Path(__file__).with_name("chat_app.py"),
             routes=[WebSocketRoute("/api/voice", voice_socket)], lifespan=lifespan)

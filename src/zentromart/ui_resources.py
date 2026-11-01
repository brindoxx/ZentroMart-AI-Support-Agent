"""Bounded public caches shared by ASGI startup and browser reruns.

Never cache a support agent, credentials, conversations, verification or tools.
Import this module inside the lifespan after Streamlit starts its runtime.
"""
from importlib import import_module
import streamlit as st
from .calculations import BusinessCalendar
from .config import load_settings, load_retrieval_settings
from .retrieval import load_search_documents, corpus_fingerprint


@st.cache_data(ttl=300, max_entries=2, show_spinner=False)
def public_data(path):
    return load_search_documents(path), BusinessCalendar.load(path)


@st.cache_resource(max_entries=2, show_spinner=False)
def public_index(path, artifacts, method, offline, corpus_sha256, embedding_model, reranker):
    from .runtime import build_public_index
    index = build_public_index(path, artifacts, method, offline, embedding_model, reranker)
    # A cached vector matrix does not load the lazy query encoder. This fixed,
    # public probe loads/tokenizes/encodes once (and warms a selected reranker).
    index.search('support', 1)
    return index


def warm_startup():
    """Local/public preparation only: no key loading or provider requests."""
    settings = load_settings()
    settings.validate_dataset_layout()
    retrieval = load_retrieval_settings(settings.project_root)
    documents, _ = public_data(settings.dataset_dir)
    public_index(str(settings.dataset_dir), str(settings.artifacts_dir),
                 retrieval.method, retrieval.offline, corpus_fingerprint(documents),
                 retrieval.embedding_model, retrieval.reranker)
    # Pre-import network SDKs without creating a credential-bearing client,
    # opening a connection, consuming quota or obtaining microphone access.
    import_module('google.genai')
    import_module('websockets.asyncio.client')

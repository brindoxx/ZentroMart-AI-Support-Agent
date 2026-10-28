"""Streamlit-only local capstone UI; run with `python -m streamlit run streamlit_app.py`."""

import streamlit as st
from collections.abc import Mapping

from zentromart.calculations import BusinessCalendar
from zentromart.config import LLMSettings, load_llm_settings, load_settings
from zentromart.retrieval import BM25Index, load_search_documents
from zentromart.tools import MockToolGateway
from zentromart.ui_text import TEXT
from zentromart.web_session import BrowserSession, ConsentModel, PublicAccessError
from zentromart.workflows import SupportAgent


st.set_page_config(page_title="ZentroMart | Support", page_icon=":material/support_agent:", layout="centered")


@st.cache_data(ttl=300, max_entries=2, show_spinner=False)
def public_data(dataset_path):
    """Only public policies/catalog and holidays are eligible for a shared cache."""
    from pathlib import Path
    path = Path(dataset_path)
    return load_search_documents(path), BusinessCalendar.load(path)


def model_settings():
    """Prefer Streamlit's server-side secret store; keep the existing .env fallback."""
    try:
        values = st.secrets["llm"]
    except (FileNotFoundError, KeyError):
        return load_llm_settings()
    if not isinstance(values, Mapping) or not all(isinstance(values.get(key), str) and values[key].strip()
                                                for key in ("provider", "model", "api_key")):
        raise ValueError("Invalid server-side model configuration")
    return LLMSettings(provider=values["provider"], model=values["model"], api_key=values["api_key"])


def handle_message(message, *, proof=False):
    session = st.session_state.support
    st.session_state.notice = None
    try:
        session.submit(message, proof=proof)
    except PublicAccessError as error:
        code = str(error)
        st.session_state.notice = code if code in {"cloud_disabled", "cloud_failed", "cloud_paused"} else "error"
    except Exception:
        # No raw exception, message, private row or executor trace is sent to the UI.
        st.session_state.notice = "error"


def verify_submission():
    proof = st.session_state.get("verification", "")
    st.session_state.verification = ""  # Callback runs before widgets render again.
    handle_message(proof, proof=True)


def clear_conversation():
    st.session_state.support.clear()
    st.session_state.notice = None
    st.session_state.verification = ""


st.session_state.setdefault("language", "en")
st.session_state.setdefault("cloud", False)
st.session_state.setdefault("tickets", False)
st.session_state.setdefault("notice", None)

with st.sidebar:
    st.subheader("ZentroMart", divider="green")
    language = st.segmented_control("Language / भाषा", ("en", "hi", "hi-en"),
                                    format_func=lambda code: {"en": "English", "hi": "हिन्दी", "hi-en": "Hinglish"}[code],
                                    key="language", required=True, width="stretch")
    if language not in TEXT:
        st.error("Choose English, Hindi, or Hinglish.")
        st.stop()
    labels = TEXT[language]
    st.caption(labels["settings"])
    cloud = st.checkbox(labels["cloud"], key="cloud", help=labels["cloud_help"])
    tickets = st.checkbox(labels["tickets"], key="tickets", help=labels["ticket_help"])
    st.caption(labels["privacy"])

st.title(labels["title"])
st.caption(labels["intro"])

try:
    settings = load_settings()
    documents, calendar = public_data(str(settings.dataset_dir))
    if "support" not in st.session_state:
        model = ConsentModel(settings_loader=model_settings)
        index = BM25Index(documents)
        gateway = MockToolGateway(settings.dataset_dir, settings.artifacts_dir / "tickets")
        agent = SupportAgent(index, model, settings.reference_date, calendar=calendar, gateway=gateway)
        st.session_state.support = BrowserSession(agent, model)
    session = st.session_state.support
    session.preferences(language, cloud=cloud, tickets=tickets)
except Exception:
    st.error(labels["error"])
    st.stop()

with st.sidebar:
    st.button(labels["clear"], key="clear", on_click=clear_conversation, icon=":material/restart_alt:", width="stretch")
    st.caption(labels["reset_note"])
    phase = session.agent.state.phase
    status = "verified" if session.agent.state.verified else {"proof": "proof", "locked": "locked"}.get(phase, "unverified")
    st.caption(labels["status"])
    st.text(labels[status])
    st.divider()
    st.caption(labels["snapshot"])

if not session.messages:
    with st.container(border=True):
        st.subheader(labels["welcome"])
        # One-shot actions; each is routed through the same backend as typed input.
        with st.container(horizontal=True):
            if st.button(labels["order"], key="start_order", icon=":material/package_2:"):
                handle_message({"en": "My order status", "hi": "मेरे ऑर्डर की स्थिति", "hi-en": "Mere order ka status"}[language])
                st.rerun()
            if st.button(labels["policy"], key="start_policy", icon=":material/assignment_return:"):
                handle_message("/policy " + {"en": "What is the fashion return window?", "hi": "कपड़ों की रिटर्न अवधि क्या है?", "hi-en": "Fashion return window kya hai?"}[language])
                st.rerun()

document_map = {doc.evidence_id: doc for doc in documents}
for message in session.messages:
    with st.chat_message(message["role"]):
        # Plain text prevents model/customer Markdown from fetching remote images.
        st.text(message["text"])
        if message["evidence"]:
            with st.expander(labels["sources"]):
                for identifier in dict.fromkeys(message["evidence"]):
                    if identifier in document_map:
                        st.caption(identifier)
                        st.text(document_map[identifier].text)

if st.session_state.notice:
    st.warning(labels.get(st.session_state.notice, labels["error"]))

if session.agent.state.phase == "proof":
    with st.form("verify", clear_on_submit=True):
        st.text_input(labels["proof_label"], key="verification", type="password", max_chars=100, autocomplete="off")
        st.form_submit_button(labels["verify"], key="verify_submit", on_click=verify_submission,
                              type="primary", icon=":material/lock:", width="stretch")
else:
    if st.button(labels["human"], key="human", icon=":material/support_agent:"):
        handle_message("/human")
        st.rerun()

st.caption(labels["commands"])
prompt = st.chat_input(labels["prompt"], key="chat", max_chars=12000,
                       disabled=session.agent.state.phase == "proof", submit_mode="disable")
if prompt:
    with st.spinner(labels["busy"]):
        handle_message(prompt)
    st.rerun()

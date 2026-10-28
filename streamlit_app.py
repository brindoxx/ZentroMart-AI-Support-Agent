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
from zentromart.demo import DemoGateway, SCENARIOS
from zentromart.voice import VoiceSession, VoiceError


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
    st.session_state.voice_audio = None
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
    clear_voice()


def clear_voice():
    st.session_state.voice_audio = None
    st.session_state.voice_notice = None
    st.session_state.voice_draft = ""
    st.session_state.recording_number = st.session_state.get("recording_number", 0) + 1


def handle_voice(action, value, language):
    """Keep only reviewed error codes; never provider messages or exceptions."""
    st.session_state.voice_notice = None
    target = "voice_draft" if action == "transcribe" else "voice_audio"
    st.session_state[target] = "" if action == "transcribe" else None
    try:
        with st.spinner(labels["voice_busy"]):
            st.session_state[target] = st.session_state.voice_session.run(action, value, language)
    except ImportError:
        st.session_state.voice_notice = (action, "dependency")
    except VoiceError as error:
        code = str(error)
        allowed = {"timeout", "authentication", "quota", "not_configured", "invalid_audio", "invalid_text", "paused"}
        st.session_state.voice_notice = (action, code if code in allowed else "error")


def retry_voice():
    st.session_state.voice_session.resume()
    st.session_state.voice_notice = None


def send_voice_message():
    text = st.session_state.get("voice_draft", "")
    clear_voice()
    handle_message(text)


def change_source():
    if "support" in st.session_state:
        st.session_state.support.clear()
    st.session_state.notice = None
    st.session_state.verification = ""
    clear_voice()


st.session_state.setdefault("language", "en")
st.session_state.setdefault("cloud", False)
st.session_state.setdefault("tickets", False)
st.session_state.setdefault("notice", None)
st.session_state.setdefault("demo", False)
st.session_state.setdefault("support_sessions", {})
st.session_state.setdefault("voice_enabled", False)
st.session_state.setdefault("voice_session", VoiceSession())
st.session_state.setdefault("voice_audio", None)
st.session_state.setdefault("voice_notice", None)
st.session_state.setdefault("voice_draft", "")
st.session_state.setdefault("recording_number", 0)

with st.sidebar:
    st.subheader("ZentroMart", divider="green")
    language = st.segmented_control("Language / भाषा", ("en", "hi", "hi-en"),
                                    format_func=lambda code: {"en": "English", "hi": "हिन्दी", "hi-en": "Hinglish"}[code],
                                    key="language", required=True, width="stretch", on_change=clear_voice)
    if language not in TEXT:
        st.error("Choose English, Hindi, or Hinglish.")
        st.stop()
    labels = TEXT[language]
    st.caption(labels["settings"])
    cloud = st.checkbox(labels["cloud"], key="cloud", help=labels["cloud_help"])
    tickets = st.checkbox(labels["tickets"], key="tickets", help=labels["ticket_help"])
    demo = st.checkbox(labels["demo"], key="demo", on_change=change_source)
    voice_enabled = st.checkbox(labels["voice"], key="voice_enabled", help=labels["voice_help"], on_change=clear_voice)
    st.caption(labels["privacy"])

st.title(labels["title"])
st.caption(labels["intro"])

try:
    settings = load_settings()
    documents, calendar = public_data(str(settings.dataset_dir))
    source = "demo" if demo else "dataset"
    sessions = st.session_state.support_sessions
    if not sessions and "support" in st.session_state:
        sessions["dataset"] = st.session_state.support
    if "ui_model" not in st.session_state:
        st.session_state.ui_model = st.session_state.support.model if "support" in st.session_state else ConsentModel(settings_loader=model_settings)
    if source not in sessions:
        model = st.session_state.ui_model
        index = BM25Index(documents)
        gateway = MockToolGateway(settings.dataset_dir, settings.artifacts_dir / ("demo-tickets" if demo else "tickets"))
        if demo:
            gateway = DemoGateway(gateway)
        agent = SupportAgent(index, model, settings.reference_date, calendar=calendar, gateway=gateway)
        sessions[source] = BrowserSession(agent, model)
    st.session_state.support = sessions[source]
    session = st.session_state.support
    session.preferences(language, cloud=cloud, tickets=tickets)
    if type(voice_enabled) is not bool:
        raise ValueError("Voice consent must be boolean")
    st.session_state.voice_session.enabled = voice_enabled
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

if voice_enabled:
    with st.expander(labels["voice_title"], expanded=True):
        st.caption(labels["voice_note"])
        waiting = session.agent.state.phase == "proof"
        recording = st.audio_input(labels["record"], sample_rate=16000,
                                   key=f"recording_{st.session_state.recording_number}", disabled=waiting)
        with st.expander(labels["mic_help"]):
            st.caption(labels["mic_note"])
            st.button(labels["recorder_reset"], key="recorder_reset", on_click=clear_voice, disabled=waiting)
            uploaded = st.file_uploader(labels["upload_wav"], type=["wav"], max_upload_size=1,
                                        key=f"voice_upload_{st.session_state.recording_number}", disabled=waiting)
        clip = uploaded if uploaded is not None else recording
        if st.button(labels["transcribe"], key="transcribe", disabled=waiting or clip is None):
            handle_voice("transcribe", clip.getvalue(), language)
        st.text_area(labels["draft"], key="voice_draft", max_chars=4000, disabled=waiting)
        st.button(labels["send_voice"], key="send_voice", on_click=send_voice_message,
                  disabled=waiting or not st.session_state.voice_draft.strip())
        latest = session.messages[-1] if session.messages and session.messages[-1]["role"] == "assistant" else None
        if st.button(labels["speak"], key="speak", disabled=waiting or latest is None or len(latest["text"]) > 800):
            handle_voice("synthesize", latest["text"], latest.get("language", language))
        if st.button(labels["test_speech"], key="test_speech", disabled=waiting):
            handle_voice("synthesize", {"en": "Hello. This is a ZentroMart voice test.",
                                       "hi": "नमस्ते। यह ज़ेंट्रोमार्ट की आवाज़ का परीक्षण है।",
                                       "hi-en": "Namaste. Yeh ZentroMart ka voice test hai."}[language], language)
        if st.session_state.voice_notice:
            action, code = st.session_state.voice_notice
            st.warning(labels["stt_error" if action == "transcribe" else "tts_error"] + " " + labels["voice_" + code])
        if st.session_state.voice_session.blocked:
            st.button(labels["voice_retry"], key="voice_retry", on_click=retry_voice, disabled=waiting)
        if st.session_state.voice_audio:
            st.audio(st.session_state.voice_audio, format="audio/wav", alt=labels["speak"])

if demo:
    with st.expander(labels["demo_title"], expanded=True):
        st.caption(labels["demo_note"])
        selected = st.selectbox(labels["scenario"], range(len(SCENARIOS)), key="demo_case",
                                format_func=lambda number: SCENARIOS[number]["title"])
        if type(selected) is not int or not 0 <= selected < len(SCENARIOS):
            st.stop()
        case = SCENARIOS[selected]
        st.text(f"Order ID: {case['id']} · {labels['demo_proof']}: {case['proof']}")
        st.caption(labels["demo_steps"])
        st.text(f"Then: {case['followup']}")
        if st.button(labels["demo_start"], key="demo_start", disabled=session.agent.state.phase == "proof"):
            session.clear()
            handle_message(case["question"] + " Order " + case["id"])
            st.rerun()

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
        if message["role"] == "assistant" and message.get("path") in {"gemini", "dialogue", "assisted", "local", "fallback", "clarification"}:
            st.caption(labels[message["path"]])
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

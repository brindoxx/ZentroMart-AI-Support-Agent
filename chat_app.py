"""Composer-first UI; explicit cloud consent once, no provider sidebar switches."""
import base64
from collections import deque
from collections.abc import Mapping
from uuid import uuid4
import streamlit as st
from zentromart.composer import composer
from zentromart.config import LLMSettings, load_settings, load_llm_settings, load_retrieval_settings
from zentromart.demo import DemoGateway, SCENARIOS
from zentromart.live_voice import REGISTRY
from zentromart.localization import DIGITS
from zentromart.retrieval import corpus_fingerprint
from zentromart.ui_resources import public_data, public_index
from zentromart.tools import MockToolGateway
from zentromart.ui_text import TEXT
from zentromart.voice import VoiceError, VoiceSession
from zentromart.web_session import BrowserSession, ConsentModel, PublicAccessError
from zentromart.workflows import submitted_proof
from zentromart.application import create_agent

st.set_page_config(page_title="ZentroMart | Support", page_icon=":material/support_agent:", layout="centered")

def model_settings():
    try:
        values = st.secrets["llm"]
    except (FileNotFoundError, KeyError):
        return load_llm_settings()
    if not isinstance(values, Mapping) or any(not isinstance(values.get(key), str) or not values[key].strip()
                                             for key in ("provider", "model", "api_key")):
        raise ValueError("Invalid server-side model configuration")
    return LLMSettings(provider=values["provider"], model=values["model"], api_key=values["api_key"])

def end_voice():
    REGISTRY.revoke(st.session_state.get("live_token"))
    st.session_state.live_token = st.session_state.live_connection = st.session_state.live_reply = None
    st.session_state.live_mode = False
    st.session_state.live_epoch += 1
    st.session_state.speech.enabled = False

def change_settings():
    end_voice()
    st.session_state.live_notice = None
    st.session_state.verification = ""

def clear_chat():
    change_settings()
    for session in st.session_state.support_sessions.values():
        session.clear()

def change_source():
    clear_chat()  # Clear verified records across demo switches; retain lockouts.

def grant_cloud_consent():
    st.session_state.chat_cloud_consent = True

def safe_notice(code):
    if not isinstance(code, str):
        return labels["voice_error"]
    if code in {"cloud_disabled", "cloud_failed", "cloud_paused"}:
        return labels[code]
    if code == "no_speech":
        return "I couldn't hear a clear phrase. Please try again."
    allowed = {"timeout", "authentication", "quota", "not_configured", "invalid_audio", "invalid_text", "paused", "consent_required"}
    return labels.get("voice_" + code, labels["voice_error"]) if code in allowed else labels["voice_error"]

def accept_event(event, channel):
    if not isinstance(event, dict) or not isinstance(event.get("id"), str) or not 1 <= len(event["id"]) <= 80:
        return False
    identity = (channel, event["id"])
    if identity in st.session_state.live_seen:
        return False
    st.session_state.live_seen.append(identity)
    return True

def submit(text, *, spoken=False):
    st.session_state.live_notice = st.session_state.live_reply = None
    try:
        if not st.session_state.chat_cloud_consent:
            raise PublicAccessError("cloud_disabled")
        if not isinstance(text, str) or not 1 <= len(text.strip()) <= 12000:
            raise ValueError("Invalid customer text")
        if spoken and submitted_proof(text.translate(DIGITS)):
            raise VoiceError("consent_required")
        with st.spinner(labels["busy"]):
            support.submit(text)
        st.session_state.language = support.agent.language
        if support.agent.state.phase in {"proof", "locked"}:
            end_voice()
            return
        latest = support.messages[-1]
        if spoken and st.session_state.live_mode:
            with st.spinner(labels["voice_synthesizing"]):
                wav = st.session_state.speech.run("synthesize", latest["text"], latest.get("language", language))
            st.session_state.live_reply = {"id": uuid4().hex, "audio": base64.b64encode(wav).decode()}
        else:
            st.session_state.live_reply = {"id": uuid4().hex}
    except Exception as error:
        end_voice()
        st.session_state.live_notice = safe_notice(str(error)) if isinstance(error, (PublicAccessError, VoiceError)) else labels["error"]

def verify():
    value = st.session_state.get("verification", "")
    st.session_state.verification = ""
    submit(value)

for name, value in (("language", "en"), ("demo", False), ("tickets", False), ("chat_cloud_consent", False),
                    ("support_sessions", {}), ("speech", VoiceSession()), ("live_token", None),
                    ("live_connection", None), ("live_reply", None), ("live_notice", None),
                    ("live_mode", False), ("live_epoch", 0), ("live_seen", deque(maxlen=64))):
    st.session_state.setdefault(name, value)

with st.sidebar:
    st.subheader("ZentroMart", divider="green")
    language = st.session_state.language
    if language not in TEXT:
        st.stop()
    labels = TEXT[language]
    st.caption("Reply language follows your messages automatically · English / हिन्दी / Hinglish")
    st.button(labels["clear"], key="clear", on_click=clear_chat, icon=":material/add:", width="stretch")
    with st.expander("Demo options"):
        demo = st.checkbox(labels["demo"], key="demo", on_change=change_source)
        tickets = st.checkbox(labels["tickets"], key="tickets")
        st.caption(labels["ticket_help"])

try:
    settings = load_settings()
    documents, calendar = public_data(settings.dataset_dir)
    retrieval = load_retrieval_settings()
    try:
        with st.spinner("Preparing document search…"):
            index = public_index(str(settings.dataset_dir), str(settings.artifacts_dir),
                                 retrieval.method, retrieval.offline, corpus_fingerprint(documents),
                                 retrieval.embedding_model, retrieval.reranker)
    except (ValueError, ImportError, OSError):
        st.error("Document search could not start. Install requirements.txt and prepare the embedding cache. "
                 "Check RETRIEVER and RETRIEVAL_OFFLINE. No fallback search method was selected.")
        st.stop()
    if "ui_model" not in st.session_state:
        st.session_state.ui_model = ConsentModel(settings_loader=model_settings)
    source, sessions = "demo" if demo else "dataset", st.session_state.support_sessions
    if source not in sessions:
        model = st.session_state.ui_model
        gateway = MockToolGateway(settings.dataset_dir, settings.artifacts_dir / ("demo-tickets" if demo else "tickets"))
        if demo:
            gateway = DemoGateway(gateway)
        dialogue = create_agent(settings, model, index=index, calendar=calendar, gateway=gateway)
        sessions[source] = BrowserSession(dialogue.backend, model, dialogue=dialogue)
    support = st.session_state.support = sessions[source]
    support.preferences(None, cloud=st.session_state.chat_cloud_consent, tickets=tickets)
except Exception:
    st.error(labels["error"])
    st.stop()

st.title("ZentroMart")
st.caption({"en": "Your AI support assistant. Type, dictate, or start a voice conversation.",
    "hi": "आपका AI सहायक। टाइप करें, बोलकर लिखें या आवाज़ में बातचीत करें।",
    "hi-en": "Aapka AI support assistant. Type karein, dictate karein ya voice conversation shuru karein."}[language])
if not st.session_state.chat_cloud_consent:
    st.info("Before starting: minimized messages and public context go to Gemini. Clicking the mic sends audio to Gnani; voice mode also sends assistant replies for speech, which may include verified synthetic order details. Use synthetic data only. Never speak verification proofs. Normal voice turns use STT and TTS credits. No transcript is saved to disk.")
    st.button("Start AI chat · allow Gemini and the voice actions I choose", key="cloud_consent", on_click=grant_cloud_consent)
if demo:
    with st.expander(labels["demo_title"]):
        for case in SCENARIOS:
            st.text(f"{case['title']} · Order {case['id']} · Test suffix {case['proof']}")

document_map = {doc.evidence_id: doc for doc in documents}
for message in support.messages:
    with st.chat_message(message["role"]):
        st.text(message["text"])
        if message["role"] == "assistant" and message.get("path") in labels:
            st.caption(labels[message["path"]])
        if message.get('diagnostic'):
            st.caption(message['diagnostic'])
        if message["evidence"]:
            with st.expander(labels["sources"]):
                for identifier in dict.fromkeys(message["evidence"]):
                    if identifier in document_map:
                        st.caption(identifier)
                        st.text(document_map[identifier].text)
waiting = support.agent.state.phase == "proof"
if waiting:
    with st.form("verify", clear_on_submit=True):
        st.text_input(labels["proof_label"], type="password", key="verification", autocomplete="off", max_chars=100)
        st.form_submit_button(labels["verify"], key="verify_submit", on_click=verify)
if st.session_state.live_notice:
    st.warning(st.session_state.live_notice)

with st.bottom:
    result = composer(disabled=waiting or not st.session_state.chat_cloud_consent, placeholder=labels["prompt"],
        connection=st.session_state.live_connection, reply=st.session_state.live_reply,
        epoch=st.session_state.live_epoch, notice=st.session_state.live_notice)

action = getattr(result, "action", None)
if action and accept_event(action, "action"):
    kind = action.get("action")
    if kind == "stop":
        end_voice()
    elif kind in {"dictate", "voice"} and st.session_state.chat_cloud_consent and not waiting and support.agent.state.phase != "locked":
        try:
            if action.get("automatic") is True and st.session_state.live_mode is not True:
                raise VoiceError("consent_required")
            REGISTRY.revoke(st.session_state.live_token)
            st.session_state.live_notice = st.session_state.live_reply = None
            st.session_state.live_mode = kind == "voice"
            speech = st.session_state.speech
            speech.enabled = True
            if action.get("automatic") is not True:
                speech.resume()
            if speech.attempts >= speech.limit or (kind == "voice" and speech.limit - speech.attempts < 2):
                raise VoiceError("paused")
            if kind == "voice" and (support.model.blocked or support.model.limit - support.model.calls < 2):
                raise VoiceError("paused")
            # en-IN is the relay's existing mixed Hindi/English, Latin-script
            # transcription path. Do not lock recognition to the previous reply.
            token = REGISTRY.issue(speech, "en", kind, action["id"])
            st.session_state.live_token = token
            st.session_state.live_connection = {"id": action["id"], "token": token}
        except VoiceError as error:
            end_voice()
            st.session_state.live_notice = safe_notice(str(error))
    st.rerun()

failure = getattr(result, "failure", None)
if failure and accept_event(failure, "failure"):
    end_voice()
    st.session_state.live_notice = safe_notice(failure.get("code"))
    st.rerun()
event = getattr(result, "submitted", None)
if event and accept_event(event, "submitted") and not waiting:
    spoken = event.get("source") == "voice"
    connection = st.session_state.live_connection
    if not spoken or (st.session_state.live_mode and connection and event["id"] == connection["id"]):
        submit(event.get("text"), spoken=spoken)
    st.rerun()

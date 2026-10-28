"""Inline CCv2 composer: native browser capture, server-relayed Gnani only."""

import streamlit as st

HTML = """
<div class="composer">
  <textarea rows="1" maxlength="12000" aria-label="Message" placeholder="How can I help?"></textarea>
  <div class="actions">
    <button class="mic" title="Dictate" aria-label="Dictate" type="button"><svg viewBox="0 0 24 24"><rect x="9" y="2" width="6" height="12" rx="3"/><path d="M5 10v2a7 7 0 0 0 14 0v-2M12 19v3m-4 0h8"/></svg></button>
    <button class="voice" title="Voice conversation" aria-label="Voice conversation" type="button"><svg viewBox="0 0 24 24"><path d="M4 9v6m4-10v14m4-17v20m4-17v14m4-10v6"/></svg></button>
    <button class="send" title="Send" aria-label="Send" type="button"><svg viewBox="0 0 24 24"><path d="m5 11 7-7 7 7M12 4v16"/></svg></button>
  </div>
</div>
<div class="status" role="status" aria-live="polite"></div>
<div class="privacy">AI assistant · Gemini + Gnani · Mic sends audio for live transcription; voice mode also sends replies for speech. Synthetic data only. Never speak verification proofs.</div>
"""

CSS = """
.composer { display:flex; gap:.4rem; align-items:flex-end; padding:.7rem; border:1px solid var(--st-border-color); border-radius:1.6rem; background:var(--st-secondary-background-color); color:var(--st-text-color); }
textarea { resize:none; flex:1; min-width:0; max-height:150px; border:0; outline:none; padding:.55rem .5rem; font:inherit; line-height:1.5; color:inherit; background:transparent; }
.actions { display:flex; align-items:center; gap:.25rem; }
button { border:0; border-radius:50%; width:42px; height:42px; color:var(--st-text-color); background:transparent; cursor:pointer; display:grid; place-items:center; }
button:hover,button[aria-pressed=true] { background:var(--st-primary-color); color:white; }
button:focus-visible { outline:2px solid var(--st-link-color); outline-offset:2px; }
button:disabled { opacity:.4; cursor:not-allowed; }
button.send { background:var(--st-primary-color); color:white; }
svg { width:22px; height:22px; fill:none; stroke:currentColor; stroke-width:1.8; stroke-linecap:round; stroke-linejoin:round; }
.status { min-height:1.3rem; font-size:.85rem; padding:.35rem .7rem 0; color:var(--st-text-color); }
.privacy { font-size:.72rem; opacity:.75; line-height:1.4; padding:.2rem .7rem; color:var(--st-text-color); }
@media(max-width:480px) { button { width:36px; height:36px; } .composer { gap:0; padding:.45rem; } }
"""

JS = """
const instances = new WeakMap();
export default function(component) {
  const {parentElement:root, data, setTriggerValue, setStateValue} = component;
  let s = instances.get(root);
  if (!s) {
    s = {mode:null, socket:null, stream:null, context:null, node:null, source:null, generation:0, prefix:'',
         timer:null, pending:null, reply:null, connection:null, draft:'', epoch:null, busy:false};
    instances.set(root,s);
  }
  const input=root.querySelector('textarea'), status=root.querySelector('.status');
  const mic=root.querySelector('.mic'), voice=root.querySelector('.voice'), send=root.querySelector('.send');
  const say = text => {status.textContent=text;};
  const releaseMic = () => {
    clearTimeout(s.timer); s.timer=null;
    s.node?.disconnect(); s.node=null;
    s.inputSource?.disconnect(); s.inputSource=null;
    s.stream?.getTracks().forEach(track=>track.stop()); s.stream=null;
  };
  const stop = (notify=false) => {
    s.generation++;
    releaseMic(); s.socket?.close(); s.socket=null;
    try {s.source?.stop();} catch (_) {} s.source=null;
    s.mode=null; s.pending=null; s.busy=false;
    mic.setAttribute('aria-pressed','false'); voice.setAttribute('aria-pressed','false');
    if(notify) setTriggerValue('action',{id:crypto.randomUUID(),action:'stop'});
  };
  const fail = code => {
    stop(); say(code==='NotAllowedError'?'Allow microphone access in your browser and Windows settings.':
      code==='no_speech'?"I couldn't hear a clear phrase. Please try again.":
      'Voice could not connect ('+code+'). Click the mic or voice button to try again.');
    setTriggerValue('failure',{id:crypto.randomUUID(),code});
  };
  const capture = async () => {
    const worklet=`class PCM extends AudioWorkletProcessor {
      constructor(){super();this.buf=[];this.pos=0;this.frame=[];}
      process(inputs){const samples=inputs[0]?.[0];if(!samples)return true;
        this.buf.push(...samples);const step=sampleRate/16000;
        while(this.pos+1<this.buf.length){const i=Math.floor(this.pos), f=this.pos-i;
          const sample=this.buf[i]*(1-f)+this.buf[i+1]*f;
          this.frame.push(Math.round(Math.max(-1,Math.min(1,sample))*32767));this.pos+=step;
          if(this.frame.length===512){const out=new ArrayBuffer(1024), view=new DataView(out);
            this.frame.forEach((x,j)=>view.setInt16(j*2,x,true));this.port.postMessage(out,[out]);this.frame=[];}}
        const consumed=Math.min(Math.floor(this.pos),Math.max(0,this.buf.length-1));this.buf.splice(0,consumed);this.pos-=consumed;return true;}}
      registerProcessor('pcm',PCM);`;
    const url=URL.createObjectURL(new Blob([worklet],{type:'text/javascript'}));
    try {await s.context.audioWorklet.addModule(url);} finally {URL.revokeObjectURL(url);}
    if(!s.mode || !s.stream) return;
    s.node=new AudioWorkletNode(s.context,'pcm');
    s.node.port.onmessage=e=> {
      if(s.socket?.readyState===WebSocket.OPEN) {
        if(s.socket.bufferedAmount>65536) {fail('connection_slow');return;}
        s.socket.send(e.data);
      }
    };
    s.inputSource=s.context.createMediaStreamSource(s.stream);
    s.inputSource.connect(s.node);s.node.connect(s.context.destination);
    say(s.mode==='voice'?'Listening… pause after your question.':'Listening… text appears as Gnani returns phrases.');
    s.timer=setTimeout(()=>finishCapture(),15000);
  };
  const finishCapture = () => {
    if(s.socket?.readyState!==WebSocket.OPEN){stop(true);say('Stopped.');return;}
    releaseMic();
    if(s.socket?.readyState===WebSocket.OPEN) s.socket.send('{"type":"stop"}');
    say('Finishing transcription…');
  };
  const request = async (mode, automatic=false) => {
    if(data.disabled || s.busy) return;
    const id=crypto.randomUUID();s.mode=mode;s.pending=id;s.busy=true;s.prefix=mode==='dictate'?input.value.trim():'';
    try {
      if(!navigator.mediaDevices?.getUserMedia) throw {name:'microphone_unavailable'};
      s.context ??= new AudioContext();await s.context.resume();
      const stream=await navigator.mediaDevices.getUserMedia({audio:{channelCount:1,echoCancellation:true,noiseSuppression:true}});
      if(s.pending!==id) {stream.getTracks().forEach(track=>track.stop());return;}
      s.stream=stream;
      mic.setAttribute('aria-pressed',String(mode==='dictate'));voice.setAttribute('aria-pressed',String(mode==='voice'));
      say('Connecting to Gnani…');
      setTriggerValue('action',{id,action:mode,automatic});
    } catch(e) {fail(e.name||'microphone_unavailable');}
  };
  if(s.epoch!==data.epoch) {stop();s.epoch=data.epoch;s.draft='';input.value='';}
  input.placeholder=data.placeholder;input.disabled=!!data.disabled || s.mode==='voice' || s.busy;
  input.setAttribute('aria-label',data.placeholder);
  mic.disabled=voice.disabled=!!data.disabled;send.disabled=!!data.disabled || !!s.mode || s.busy;
  if(data.disabled) stop();
  if(data.notice) {stop();say(data.notice);}
  input.oninput=()=>{s.draft=input.value;input.style.height='auto';input.style.height=Math.min(input.scrollHeight,150)+'px';};
  const submit = () => {
    const text=input.value.trim();if(!text || data.disabled || s.mode || s.busy)return;
    input.value='';s.draft='';s.busy=true;input.disabled=true;send.disabled=true;say('Getting a reply…');
    setStateValue('draft','');setTriggerValue('submitted',{id:crypto.randomUUID(),text,source:'typed'});
  };
  send.onclick=submit;input.onkeydown=e=>{if(e.key==='Enter'&&!e.shiftKey&&!e.isComposing){e.preventDefault();submit();}};
  mic.onclick=()=>{if(s.mode==='dictate')finishCapture();else if(s.mode)stop(true);else request('dictate');};
  voice.onclick=()=>{if(s.mode)stop(true);else request('voice');};
  const connection=data.connection;
  if(connection && connection.id===s.pending && connection.id!==s.connection) {
    s.connection=connection.id;
    const url=new URL('/api/voice',window.location.href);url.protocol=location.protocol==='https:'?'wss:':'ws:';
    const socket=s.socket=new WebSocket(url);
    socket.onopen=()=>socket.send(JSON.stringify({token:connection.token}));
    socket.onerror=()=>fail('connection_failed');
    socket.onclose=()=>{if(s.socket===socket && s.stream)fail('connection_closed');};
    socket.onmessage=async event=>{
      if(s.socket!==socket)return;
      let msg;try {msg=JSON.parse(event.data);}catch(_){fail('invalid_response');return;}
      if(msg.type==='ready') {try{await capture();}catch(e){fail(e.name||'microphone_unavailable');}}
      if(msg.type==='processing')say('Gnani is transcribing your phrase…');
      if(msg.type==='transcript') {s.draft=[s.prefix,msg.text].filter(Boolean).join(' ');input.value=s.draft;}
      if(msg.type==='error')fail(msg.code);
      if(msg.type==='complete') {
        releaseMic();s.socket=null;socket.close();s.busy=false;
        const mode=s.mode;s.pending=null;
        if(mode==='voice') {
          s.busy=true;input.value='';s.draft='';say('Getting a spoken reply…');
          setTriggerValue('submitted',{id:msg.id,text:msg.text,source:'voice'});
        } else {
          s.mode=null;mic.setAttribute('aria-pressed','false');send.disabled=false;
          s.draft=[s.prefix,msg.text].filter(Boolean).join(' ');input.value=s.draft;setStateValue('draft',s.draft);say('Edit your message, then Send.');
        }
      }
    };
  }
  const reply=data.reply;
  if(reply && reply.id!==s.reply) {
    s.reply=reply.id;s.busy=false;input.disabled=!!data.disabled || s.mode==='voice';send.disabled=!!data.disabled || !!s.mode;
    if(reply.audio && s.context) {
      const generation=s.generation;
      const bytes=Uint8Array.from(atob(reply.audio),c=>c.charCodeAt(0));
      s.context.decodeAudioData(bytes.buffer).then(buffer=>{
        if(s.mode!=='voice' || data.disabled || generation!==s.generation)return;
        const source=s.source=s.context.createBufferSource();source.buffer=buffer;source.connect(s.context.destination);
        source.onended=()=>{if(s.mode==='voice' && s.source===source){s.source=null;request('voice',true);}};
        source.start();say('Speaking… click voice to end.');
      }).catch(()=>fail('playback_failed'));
    } else if(s.mode==='voice') {stop();say(reply.message||'Voice paused. Read the answer in chat.');}
    else if(!data.notice)say('');
  }
  return ()=>{stop();s.context?.close();instances.delete(root);};
}
"""

_COMPONENT = st.components.v2.component("zentromart_live_composer", html=HTML, css=CSS, js=JS)


def composer(*, disabled, placeholder, connection, reply, epoch, notice=None):
    return _COMPONENT(key="live_composer", data={"disabled": disabled, "placeholder": placeholder,
                      "connection": connection, "reply": reply, "epoch": epoch, "notice": notice},
                      on_action_change=lambda: None, on_submitted_change=lambda: None,
                      on_failure_change=lambda: None, on_draft_change=lambda: None)

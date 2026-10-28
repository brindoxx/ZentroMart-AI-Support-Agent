// Local browser-state tests with fake microphone/WebSocket/audio APIs. No network.
import fs from 'node:fs';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import {webcrypto} from 'node:crypto';

const source=fs.readFileSync(new URL('../src/zentromart/composer.py',import.meta.url),'utf8');
const js=source.match(/JS = """\n([\s\S]*?)\n"""/)[1];
const {default:mount}=await import('data:text/javascript;base64,'+Buffer.from(js).toString('base64'));
Object.defineProperty(globalThis,'crypto',{value:webcrypto,configurable:true});
globalThis.location={protocol:'http:'};
globalThis.window={location:{href:'http://127.0.0.1:8502/'}};
const ticks=async()=>{for(let i=0;i<5;i++)await new Promise(resolve=>setImmediate(resolve));};
let tracks=[],contexts=[],sockets=[],workletSource='';
Object.defineProperty(globalThis,'navigator',{value:{mediaDevices:{getUserMedia:async()=>{
  const track={stopped:false,stop(){this.stopped=true;}};tracks.push(track);
  return {getTracks:()=>[track]};
}}},configurable:true});
globalThis.AudioContext=class {
  constructor(){contexts.push(this);this.sources=[];this.destination={};this.audioWorklet={addModule:async url=>{
    workletSource=await (await fetch(url)).text();
  }};}
  async resume(){} async close(){} async decodeAudioData(){return {};}
  createMediaStreamSource(){return {connect(){},disconnect(){}};}
  createBufferSource(){const source={connect(){},start(){this.started=true;},stop(){this.stopped=true;}};this.sources.push(source);return source;}
};
globalThis.AudioWorkletNode=class {
  constructor(){this.port={};}connect(){}disconnect(){}
};
globalThis.WebSocket=class {
  static OPEN=1;
  constructor(url){this.url=url;this.readyState=1;this.bufferedAmount=0;this.sent=[];sockets.push(this);queueMicrotask(()=>this.onopen?.());}
  send(value){this.sent.push(value);}close(){this.closed=true;this.readyState=3;}
  async event(value){await this.onmessage?.({data:JSON.stringify(value)});await ticks();}
};
function fixture(){
  const node=()=>({value:'',textContent:'',style:{},attrs:{},setAttribute(key,value){this.attrs[key]=value;}});
  const nodes={textarea:node(),'.status':node(),'.mic':node(),'.voice':node(),'.send':node()};
  const root={querySelector:key=>nodes[key]},events=[],state=[];
  const data={disabled:false,placeholder:'Message',epoch:0};
  const component={parentElement:root,data,setTriggerValue:(key,value)=>events.push([key,value]),setStateValue:(key,value)=>state.push([key,value])};
  let cleanup=mount(component);
  return {nodes,events,state,data,render(update={}){Object.assign(data,update);cleanup=mount({...component,data:{...data}});},cleanup:()=>cleanup()};
}
async function connect(f,mode){
  await f.nodes[mode==='voice'?'.voice':'.mic'].onclick();await ticks();
  const action=f.events.filter(e=>e[0]==='action').at(-1)[1];
  f.render({connection:{id:action.id,token:'LOCAL-CAPABILITY-NOT-PROVIDER-KEY'}});await ticks();
  const socket=sockets.at(-1);
  assert.equal(JSON.parse(socket.sent[0]).token,'LOCAL-CAPABILITY-NOT-PROVIDER-KEY');
  await socket.event({type:'ready'});
  return {socket,action};
}

// Typed Send is at-most-once until a response, and Enter uses the same handler.
{
  const f=fixture();f.nodes.textarea.value='hello';f.nodes['.send'].onclick();f.nodes['.send'].onclick();
  assert.equal(f.events.filter(e=>e[0]==='submitted').length,1);
  f.render({reply:{id:'text-reply'}});assert.equal(f.nodes.textarea.disabled,false);
  f.cleanup();
}
// Dictation shows Gnani text in the composer but does not auto-send it.
{
  const f=fixture();f.nodes.textarea.value='Please help with';
  const {socket}=await connect(f,'dictate');
  await socket.event({type:'transcript',text:'my return'});
  assert.equal(f.nodes.textarea.value,'Please help with my return');
  await socket.event({type:'complete',text:'my return',id:'mic-turn'});
  assert.equal(f.events.filter(e=>e[0]==='submitted').length,0);
  assert.equal(tracks.at(-1).stopped,true);
  assert.equal(f.nodes.textarea.value,'Please help with my return');
  f.nodes['.send'].onclick();assert.equal(f.events.at(-1)[1].text,'Please help with my return');
  f.cleanup();
}
// Voice sends after VAD, plays once and resumes only after playback ends.
{
  const f=fixture();const {socket,action}=await connect(f,'voice');
  await socket.event({type:'transcript',text:'Where is my parcel?'});
  await socket.event({type:'complete',text:'Where is my parcel?',id:action.id});
  const sent=f.events.filter(e=>e[0]==='submitted');assert.equal(sent.length,1);assert.equal(sent[0][1].source,'voice');
  const reply={id:'spoken-reply',audio:Buffer.from('RIFFmock').toString('base64')};
  f.render({reply});await ticks();
  assert.equal(contexts.at(-1).sources.length,1);assert.equal(contexts.at(-1).sources[0].started,true);
  f.render({reply});await ticks();assert.equal(contexts.at(-1).sources.length,1);
  const before=f.events.length;contexts.at(-1).sources[0].onended();await ticks();
  assert.equal(f.events.length,before+1);assert.equal(f.events.at(-1)[1].automatic,true);
  f.nodes['.voice'].onclick();assert.equal(tracks.at(-1).stopped,true);
  f.cleanup();
}
// An ended/stopped stream cannot inject a late transcript or restart capture.
{
  const f=fixture();const {socket}=await connect(f,'voice');
  f.nodes['.voice'].onclick();
  await socket.event({type:'complete',text:'STALE',id:'old'});
  assert.equal(f.events.filter(e=>e[0]==='submitted').length,0);
  f.cleanup();
}
// The real worklet emits 16-kHz little-endian PCM at 44.1/48-kHz input rates.
{
  const previous=navigator.mediaDevices.getUserMedia;
  let resolvePermission;
  navigator.mediaDevices.getUserMedia=()=>new Promise(resolve=>{resolvePermission=resolve;});
  const f=fixture();f.nodes['.mic'].onclick();await ticks();
  f.nodes['.voice'].onclick(); // Cancel while the browser permission promise is pending.
  const track={stopped:false,stop(){this.stopped=true;}};
  resolvePermission({getTracks:()=>[track]});await ticks();
  assert.equal(track.stopped,true);
  assert.equal(f.events.filter(e=>e[0]==='action'&&e[1].action==='dictate').length,0);
  f.cleanup();navigator.mediaDevices.getUserMedia=previous;
}
for(const rate of [44100,48000]){
  let Processor;
  const frames=[];
  vm.runInNewContext(workletSource,{sampleRate:rate,AudioWorkletProcessor:class{
    constructor(){this.port={postMessage:buffer=>frames.push(buffer)};}
  },registerProcessor:(name,cls)=>{Processor=cls;}});
  const processor=new Processor();
  for(let offset=0;offset<rate;offset+=128)processor.process([[new Float32Array(Math.min(128,rate-offset)).fill(.5)]]);
  const samples=frames.length*512+processor.frame.length;
  assert.ok(Math.abs(samples-16000)<=2,`${rate} resampled to ${samples}`);
  assert.ok(frames.every(buffer=>buffer.byteLength===1024));
  assert.ok(Math.abs(new DataView(frames[0]).getInt16(0,true)-16384)<=1);
}
console.log('PASS: typed send, live dictation, VAD voice turns, playback deduplication, stop/late-event safety and 44.1/48-kHz PCM resampling.');

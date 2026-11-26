"use strict";
const profiles = {
  interrupted: "512 KiB file · 600 KiB/s · One disconnect at 70% · 64 KiB checkpoints",
  stable: "512 KiB file · 2 MiB/s · Stable connection · 64 KiB checkpoints",
  latency: "512 KiB file · 2 MiB/s · 200 ms request overhead · 64 KiB checkpoints",
  small: "32 KiB file · 2 MiB/s · Stable connection · 64 KiB checkpoints"
};
const strategies = {
  whole: {label:"Whole file", variant:"A / CONTROL", method:"After a disconnect, start again from byte zero.", accent:"#ecc4a0"},
  resume: {label:"Resumable", variant:"B / VARIANT", method:"Keep confirmed chunks and restart at the last checkpoint.", accent:"#c8ef72"}
};
const plots = {};
const form = document.querySelector("#controls");
const button = document.querySelector("#run");
const note = document.querySelector("#profile-note");
const statusLine = document.querySelector("#run-status");
const selected = () => form.elements.scenario.value;
const scenarioText = () => { note.textContent = profiles[selected()] + " · 4× slower for viewing"; };
form.addEventListener("change", () => {
  scenarioText();
  for (const key of Object.keys(strategies)) reset(key);
  document.querySelector("#source-hash").textContent = "Awaiting transfer";
  document.querySelector("#button-label").textContent = "Run comparison";
  statusLine.classList.remove("error");
  statusLine.textContent = "Ready to run the selected profile.";
});
scenarioText();
function draw(key) {
  const plot = plots[key];
  const canvas = plot.card.querySelector("canvas");
  const w = canvas.clientWidth, h = canvas.clientHeight;
  const dpr = Math.min(window.devicePixelRatio || 1, 2);
  canvas.width = Math.round(w * dpr); canvas.height = Math.round(h * dpr);
  const ctx = canvas.getContext("2d");
  ctx.scale(dpr,dpr);
  const left=2, top=4, right=w-4, bottom=h-4;
  for(let i=0;i<=4;i++){
    const y=top+(bottom-top)*i/4;
    ctx.strokeStyle="#2e3d46";ctx.lineWidth=1;ctx.setLineDash([2,4]);
    ctx.beginPath();ctx.moveTo(left,y);ctx.lineTo(right,y);ctx.stroke();
    const x=left+(right-left)*i/4;
    ctx.beginPath();ctx.moveTo(x,top);ctx.lineTo(x,bottom);ctx.stroke();
  }
  ctx.setLineDash([]);
  const extent = Math.max(plot.deadline, ...plot.samples.map(p => p.t));
  const coords = plot.samples.map(p => ({x:left+(right-left)*p.t/extent,y:bottom-(bottom-top)*p.r}));
  if(coords.length) {
    ctx.beginPath();ctx.moveTo(left,bottom);
    for(const p of coords)ctx.lineTo(p.x,p.y);
    const last=coords.at(-1);
    ctx.lineTo(last.x,bottom);ctx.closePath();ctx.fillStyle=strategies[key].accent+"20";ctx.fill();
    ctx.beginPath();ctx.moveTo(left,bottom);
    for(const p of coords)ctx.lineTo(p.x,p.y);
    ctx.strokeStyle=strategies[key].accent;ctx.lineWidth=2.2;ctx.lineJoin="round";ctx.stroke();
    ctx.beginPath();ctx.arc(last.x,last.y,3,0,2*Math.PI);ctx.fillStyle=strategies[key].accent;ctx.fill();
  }
  for(const t of plot.drops){
    const x=left+(right-left)*t/extent;
    ctx.setLineDash([3,3]);ctx.lineWidth=1.2;ctx.strokeStyle="#ef9770";ctx.beginPath();ctx.moveTo(x,top);ctx.lineTo(x,bottom);ctx.stroke();ctx.setLineDash([]);
  }
  plot.card.querySelector(".axis-max").textContent = (extent/1000).toFixed(1)+" s";
}
function setState(card,label,tone="") {
  const state=card.querySelector(".state");state.textContent=label;state.dataset.state=tone;
}
function reset(key) {
  const plot=plots[key], card=plot.card;
  plot.samples=[];plot.drops=[];plot.deadline=5000;plot.finished=false;
  for(const field of ["sent","elapsed","retries"])card.querySelector("."+field).textContent="—";
  card.querySelector(".pct").textContent="0%";setState(card,"Ready");
  document.getElementById(key+"-hash").textContent="Awaiting transfer";
  const verdict=document.getElementById(key+"-verdict");verdict.textContent="—";verdict.className="";
  draw(key);
}
for (const [key,def] of Object.entries(strategies)) {
  const card=document.querySelector("#card").content.firstElementChild.cloneNode(true);
  card.classList.add(key);card.querySelector("h2").textContent=def.label;
  card.querySelector(".variant").textContent=def.variant;card.querySelector(".method").textContent=def.method;
  document.querySelector("#cards").append(card);plots[key]={card};reset(key);
  new ResizeObserver(()=>draw(key)).observe(card.querySelector("canvas"));
}
function bytes(n){return (n/1024).toLocaleString("en-US",{maximumFractionDigits:1})+" KiB";}
function processEvent(e){
  if(e.error)throw new Error(e.error);
  const p=plots[e.strategy];if(!p)return;
  const card=p.card, t=Number(e.elapsed_ms)||0;
  const ratio=Math.min(1, Math.max(0,(Number(e.progress_bytes)||0)/(Number(e.size_bytes)||1)));
  if(e.deadline_ms)p.deadline=e.deadline_ms;
  p.samples.push({t,r:ratio});
  card.querySelector(".pct").textContent=Math.round(ratio*100)+"%";
  card.querySelector(".sent").textContent=bytes(e.wire_bytes||0);
  card.querySelector(".elapsed").textContent=(t/1000).toFixed(2)+" s";
  if(e.expected_sha256)document.querySelector("#source-hash").textContent=e.expected_sha256;
  if(e.event==="disconnect"){p.drops.push(t);setState(card,"Disconnected","warning");}
  else if(e.event==="finish"){
    p.finished=true;
    setState(card,e.success?"Verified":(e.reason==="deadline"?"Deadline reached":"Incomplete"),e.success?"success":"warning");
    document.getElementById(e.strategy+"-hash").textContent=e.sha256||"Incomplete file";
    const verdict=document.getElementById(e.strategy+"-verdict");
    verdict.textContent=e.success?"Verified on time":(e.verified?"Verified late":(e.reason||"Incomplete"));
    verdict.className=e.success?"good":"bad";
  } else {setState(card,p.drops.length?"Recovering":"Uploading");}
  card.querySelector(".retries").textContent=p.drops.length;
  draw(e.strategy);
}
form.addEventListener("submit", async ev=>{
  ev.preventDefault();if(button.disabled)return;
  const scenario=selected();
  button.disabled=true;for(const input of form.querySelectorAll("input"))input.disabled=true;
  for(const key of Object.keys(strategies))reset(key);
  document.querySelector("#source-hash").textContent="Awaiting transfer";
  document.querySelector("#button-label").textContent="Running…";
  statusLine.classList.remove("error");statusLine.textContent="Two uploads in progress. The dotted vertical marker records a disconnect.";
  try{
    const response=await fetch("/api/demo",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({scenario,pace:"demo"})});
    if(!response.ok)throw new Error("Transfer service returned HTTP "+response.status);
    const reader=response.body.getReader(), decoder=new TextDecoder();let pending="";
    const parse=line=>{if(line.trim())processEvent(JSON.parse(line));};
    while(true){
      const {done,value}=await reader.read();if(done)break;
      pending+=decoder.decode(value,{stream:true});const lines=pending.split("\n");pending=lines.pop();lines.forEach(parse);
    }
    parse(pending+decoder.decode());
    if(!Object.values(plots).every(p=>p.finished))throw new Error("Connection closed before both receipts arrived");
    statusLine.textContent="Paired run complete. Compare the server receipts below.";
  }catch(err){
    statusLine.classList.add("error");statusLine.textContent="Run interrupted. "+err.message+". You can retry this comparison.";
    for(const p of Object.values(plots))if(!p.finished)setState(p.card,"Stopped","warning");
  }finally{
    button.disabled=false;for(const input of form.querySelectorAll("input"))input.disabled=false;
    document.querySelector("#button-label").textContent="Run again";
  }
});

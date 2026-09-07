import { seededRandom, generateGraph, planRun, edgePoint } from './graph.js';

export const STAGES=Object.freeze({prepareEnd:1.6,flowStart:1.6,flowEnd:3.6,recordEnd:7.1,archiveStart:8.5,archiveEnd:10,paintStart:10.2,paintEnd:15.5,handoffEnd:16.8,cycle:17.5});
const tau=Math.PI*2;
const mix=(a,b,t)=>a+(b-a)*t;
const clamp=x=>Math.max(0,Math.min(x,1));
const smooth=x=>{const p=clamp(x);return p*p*(3-2*p);};
const ramp=(x,a,b)=>smooth((x-a)/(b-a));
const cubic=(a,b,c,d,p)=>[0,1].map(i=>(1-p)**3*a[i]+3*(1-p)**2*p*b[i]+3*(1-p)*p*p*c[i]+p**3*d[i]);
const pill=(node,p)=>[node.x+Math.cos(p*tau)*16,node.y+Math.sin(p*tau)*9];
const graphOffsetY=-175;
const graphBottomY=337+(439-337)*.8+graphOffsetY+9;
const graphHeight=(439-215)*.8+18;
const placeGraphPoint=([x,y],offsetY,scaleX,scaleY)=>[50+(x-50)*scaleX,graphBottomY+(y-graphBottomY)*scaleY+offsetY];
export const spanPosition=(point,depth)=>[733+(point.x-733)*(1-depth*.05)+depth*26,340+(point.y-340)*(1-depth*.05)-depth*25];
export const graphPosition=(point,depth)=>[270+(point[0]-270)*(1-depth*.055)+depth*16,337+graphOffsetY+(point[1]-337-graphOffsetY)*(1-depth*.055)-depth*27];

export function buildStagedRun(graph,rng) {
  const raw=planRun(graph,rng,'softroutes');
  const scale=2/(raw.end-1);
  const events=raw.events.map(event=>({...event,start:STAGES.flowStart+(event.start-1)*scale,duration:event.duration*scale}));
  const rows=[{depth:0,parent:null,event:events[0],start:STAGES.flowStart,end:STAGES.flowEnd,x:562,width:402}];
  events.forEach((event,i)=>{
    if(event.type!=='node')return;
    const edge=events[i+1]?.type==='edge'?events[i+1]:null;
    const parentIndex=rows.length;
    const parent={depth:1,parent:0,event,start:event.start,end:event.start+event.duration+(edge?.duration??0),x:590+(event.start-STAGES.flowStart)*12,width:284+rng()*46};
    rows.push(parent);
    // Repeated sibling operations keep nesting visible without textual labels.
    for(let peer=0;peer<3;peer++) {
      const emitter=peer===2&&edge?edge:event;
      const start=emitter===edge?edge.start:event.start+peer/3*event.duration;
      const end=emitter===edge?edge.start+edge.duration:start+event.duration/3;
      rows.push({depth:2,parent:parentIndex,event:emitter,start,end,x:parent.x+26,width:parent.width*(.47+rng()*.32)});
    }
  });
  const particles=[];
  rows.forEach((row,rowIndex)=>{
    row.y=8+rowIndex/(rows.length-1)*634;
    row.width*=1.5;
    const count=Math.floor(row.width/5.8)+1;
    for(let col=0;col<count;col++) {
      const origin=row.event.type==='node'?pill(graph.nodes[row.event.id],rng()):edgePoint(graph,graph.edges[row.event.id],rng(),'softroutes');
      particles.push({x:row.x+col/(count-1)*row.width,y:row.y,row:rowIndex,col,origin,event:row.event,departure:STAGES.flowEnd,flight:2.3+rng()*1.2,bend:(rng()-.5)*170,drift:(rng()-.5)*65,radius:col===0?2:col%13===0?1.6+rng()*.25:.7+rng()*.55,opacity:col===0?.95:.26+rng()*.65,warm:rng()<.026||col===0});
    }
  });
  return {events,rows,particles};
}

export function stagedParticlePosition(particle,age,graphOffset=0,graphScaleX=1,graphScaleY=1) {
  if(age<particle.departure)return null;
  const p=ramp(age,particle.departure,particle.departure+particle.flight);
  const source=placeGraphPoint(particle.origin,graphOffset,graphScaleX,graphScaleY),target=[particle.x,particle.y];
  return cubic(source,[source[0]+95+particle.drift,source[1]+particle.bend],[target[0]-105,target[1]-particle.bend*.3],target,p);
}

export function traversalPosition(item,clock) {
  const event=item.run.events.find(event=>clock>=event.start&&clock<=event.start+event.duration);
  if(!event)return null;
  const p=ramp(clock,event.start,event.start+event.duration);
  if(event.type==='edge')return edgePoint(item.graph,item.graph.edges[event.id],p,'softroutes');
  const node=item.graph.nodes[event.id];
  return [node.x-17+p*34,node.y];
}

export const graphHandoff=age=>ramp(age,STAGES.paintEnd,STAGES.handoffEnd);

// Cache the soft light once per scene rather than blurring thousands of dots
// every frame. The crisp centers are drawn separately at their actual size.
function glowSprite(color) {
  const canvas=document.createElement('canvas');
  canvas.width=canvas.height=64;
  const ctx=canvas.getContext('2d');
  const gradient=ctx.createRadialGradient(32,32,0,32,32,32);
  for(const [stop,alpha] of [[0,.7],[.12,.5],[.3,.18],[.6,.035],[1,0]])gradient.addColorStop(stop,`rgba(${color},${alpha})`);
  ctx.fillStyle=gradient;ctx.fillRect(0,0,64,64);
  return canvas;
}

export function createStagedRoutes(seed=Math.floor(Math.random()*4294967296)) {
  const colors={blue:'83,143,255',warm:'255,166,86',yellow:'255,216,99'};
  const highlights={blue:'211,233,255',warm:'255,229,190',yellow:'255,246,215'};
  const glows=Object.fromEntries(Object.entries(colors).map(([tone,color])=>[tone,glowSprite(color)]));
  const models=new Map();
  function model(generation) {
    if(models.has(generation))return models.get(generation);
    const rng=seededRandom(seed+Math.imul(generation,15485863));
    const previous=models.get(generation-1);
    let graph;
    do{graph=generateGraph(rng,'softroutes');}while(previous&&graph.signature===previous.graph.signature);
    for(const node of graph.nodes)node.y=337+(node.y-337)*.8+graphOffsetY;
    const run=buildStagedRun(graph,rng);
    const ink=[];
    for(const node of graph.nodes)for(let i=0;i<38;i++)ink.push(pill(node,i/38));
    for(const edge of graph.edges)for(let i=0;i<48;i++)ink.push(edgePoint(graph,edge,i/47,'softroutes'));
    const paint=ink.map((target,i)=>({target,slot:i%4,sample:rng(),departure:STAGES.paintStart+rng()*.55+(i%4)*.1,flight:3+rng()*1.3,bend:(rng()-.5)*60}));
    const item={graph,run,ink,paint};models.set(generation,item);return item;
  }
  return (ctx,time,graphBottom,graphRight=497)=>{
    // Anchor the lowest swimlane's outline above the hero, in canvas units.
    const offsetY=graphBottom===undefined?0:graphBottom-graphBottomY;
    const scaleX=(graphRight-50)/(497-50);
    const scaleY=graphBottom===undefined?1:Math.max(0,Math.min(1,graphBottom/graphHeight));
    const placeGraph=point=>placeGraphPoint(point,offsetY,scaleX,scaleY);
    const generation=Math.floor(time/STAGES.cycle),age=time%STAGES.cycle;
    for(let id=generation-4;id<=generation+1;id++)model(id);
    for(const id of models.keys())if(id<generation-4)models.delete(id);
    const current=model(generation),next=model(generation+1);
    const past=Array.from({length:4},(_,i)=>model(generation-1-i));
    ctx.save();
    ctx.globalCompositeOperation='lighter';
    const dot=(x,y,r,alpha=.85,tone='blue')=>{
      if(alpha<=0)return;
      const halo=r*5;
      ctx.globalAlpha=alpha;
      ctx.drawImage(glows[tone],x-halo,y-halo,halo*2,halo*2);
      ctx.globalAlpha=1;
      ctx.fillStyle=`rgba(${colors[tone]},${alpha})`;
      ctx.beginPath();ctx.arc(x,y,r,0,tau);ctx.fill();
      ctx.fillStyle=`rgba(${highlights[tone]},${alpha*.82})`;
      ctx.beginPath();ctx.arc(x,y,r*.48,0,tau);ctx.fill();
    };
    const line=(points,alpha=.2,yellow=false,width=1)=>{
      if(alpha<=0)return;
      const tone=yellow?'yellow':'blue';
      ctx.beginPath();points.forEach(([x,y],i)=>i?ctx.lineTo(x,y):ctx.moveTo(x,y));
      for(const [spread,strength] of [[5,.055],[2,.15],[0,1]]) {
        ctx.strokeStyle=`rgba(${colors[tone]},${alpha*strength})`;
        ctx.lineWidth=width+spread;ctx.stroke();
      }
      ctx.strokeStyle=`rgba(${highlights[tone]},${alpha*.38})`;
      ctx.lineWidth=width*.45;ctx.stroke();
    };
    const graphOpacities=[.86,.25,.075,.035,.014,0];
    const spanOpacities=[.86,.12,.028,.004,0];
    const opacity=(depth,stops)=>{const low=Math.floor(depth);return mix(stops[low],stops[Math.min(low+1,stops.length-1)],depth-low);};
    function trace(item,depth,alpha) {
      for(const p of item.run.particles)dot(...spanPosition(p,depth),p.radius*(1-depth*.05),alpha*p.opacity,p.warm?'warm':'blue');
    }
    function graph(item,depth,alpha,clock,active=0) {
      const project=p=>placeGraph(graphPosition(p,depth));
      const foreground=1-clamp(depth);
      const nodeEvents=new Map(item.run.events.filter(e=>e.type==='node').map(e=>[e.id,e]));
      const edgeEvents=new Map(item.run.events.filter(e=>e.type==='edge').map(e=>[e.id,e]));
      for(const edge of item.graph.edges) {
        const points=Array.from({length:45},(_,i)=>edgePoint(item.graph,edge,i/44,'softroutes'));
        line(points.map(project),alpha*(.37+foreground*.18));
        const last=points.at(-1);line([[last[0]-4,last[1]-3],last,[last[0]-4,last[1]+3]].map(project),alpha*.42);
        const event=edgeEvents.get(edge.id);
        if(active&&event&&clock>=event.start) {
          const p=ramp(clock,event.start,event.start+event.duration);
          const selected=Array.from({length:Math.ceil(p*44)+1},(_,i)=>edgePoint(item.graph,edge,Math.min(i/44,p),'softroutes'));
          selected.push(edgePoint(item.graph,edge,p,'softroutes'));
          line(selected.map(project),alpha*active,true,1.5);
        }
      }
      for(const node of item.graph.nodes) {
        const event=nodeEvents.get(node.id);
        const border=Array.from({length:41},(_,i)=>pill(node,i/40));
        line(border.map(project),alpha*(.85+foreground*.1),false,1.2);
        if(active&&event)line(border.map(project),alpha*active*ramp(clock,event.start,event.start+event.duration),true,1.2);
      }
      const head=active?traversalPosition(item,clock):null;
      if(head) {
        const glow=alpha*active*ramp(clock,STAGES.flowStart,STAGES.flowStart+.12)*(1-ramp(clock,STAGES.flowEnd-.12,STAGES.flowEnd));
        dot(...project(head),7,glow*.08,'yellow');
        dot(...project(head),4,glow*.22,'yellow');
        dot(...project(head),2,glow,'yellow');
      }
    }

    // 1. Complete the span-history movement before graph execution can start.
    const spanShift=ramp(age,0,1.35);
    for(let slot=3;slot>=0;slot--) {
      const depth=slot+spanShift;
      let alpha=opacity(depth,spanOpacities);
      if(slot===3)alpha*=1-ramp(age,0,.7);
      if(alpha>0)trace(past[slot],depth,alpha);
    }
    // The new trace has no visible scaffold. Its first marks are arriving dots,
    // including the orange particle that becomes the start of each span.

    // Keep historical graph versions, rather than dissolving the old graph.
    const graphShift=ramp(age,STAGES.archiveStart,STAGES.archiveEnd);
    for(let slot=3;slot>=0;slot--) {
      const depth=slot+1+graphShift;
      const alpha=opacity(depth,graphOpacities);
      if(alpha>0)graph(past[slot],depth,alpha,0,false);
    }
    const active=1-ramp(age,STAGES.archiveStart-.25,STAGES.archiveEnd-.25);
    graph(current,graphShift,opacity(graphShift,graphOpacities),age,active);

    // 2. The route consumes exactly two seconds. No particles exist in flight.
    // 3. Every sampled active node/edge releases its particles at the same time.
    for(const particle of current.run.particles) {
      const pos=stagedParticlePosition(particle,age,offsetY,scaleX,scaleY);
      if(!pos)continue;
      const birth=ramp(age,particle.departure,particle.departure+.2);
      dot(...pos,particle.radius,.86*particle.opacity*birth,particle.warm?'warm':'blue');
    }

    // 4. The graph's recession finishes before evidence paints its new version.
    if(age>=STAGES.paintStart) {
      const evidence=[current,...past.slice(0,3)];
      const handoff=graphHandoff(age);
      for(const particle of next.paint) {
        if(age<particle.departure)continue;
        const tracePoints=evidence[particle.slot].run.particles;
        const point=tracePoints[Math.floor(particle.sample*tracePoints.length)];
        const source=spanPosition(point,particle.slot);
        const p=ramp(age,particle.departure,particle.departure+particle.flight);
        const target=placeGraph(particle.target);
        const pos=cubic(source,[520,source[1]+particle.bend],[target[0]+70,target[1]],target,p);
        dot(...pos,1.08,ramp(age,particle.departure,particle.departure+.22)*.75*(1-handoff));
      }
      // The settled dots share the outline's geometry, then crossfade completely
      // into its strokes before rollover. Nothing disappears on the cycle edge.
      if(handoff>0)graph(next,0,handoff*.86,0);
    }
    ctx.restore();
  };
}

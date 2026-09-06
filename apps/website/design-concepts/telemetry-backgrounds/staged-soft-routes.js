import { seededRandom, generateGraph, planRun, edgePoint } from './swimlane-studies.js';

export const STAGES=Object.freeze({prepareEnd:1.6,flowStart:1.6,flowEnd:3.6,recordEnd:7.1,archiveStart:8.5,archiveEnd:10,paintStart:10.2,paintEnd:15.5,cycle:17.5});
const tau=Math.PI*2;
const mix=(a,b,t)=>a+(b-a)*t;
const clamp=x=>Math.max(0,Math.min(x,1));
const smooth=x=>{const p=clamp(x);return p*p*(3-2*p);};
const ramp=(x,a,b)=>smooth((x-a)/(b-a));
const cubic=(a,b,c,d,p)=>[0,1].map(i=>(1-p)**3*a[i]+3*(1-p)**2*p*b[i]+3*(1-p)*p*p*c[i]+p**3*d[i]);
const pill=(node,p)=>[node.x+Math.cos(p*tau)*16,node.y+Math.sin(p*tau)*9];
export const spanPosition=(point,depth)=>[733+(point.x-733)*(1-depth*.05)+depth*26,340+(point.y-340)*(1-depth*.05)-depth*25];
export const graphPosition=(point,depth)=>[270+(point[0]-270)*(1-depth*.055)+depth*16,337+(point[1]-337)*(1-depth*.055)-depth*27];

export function buildStagedRun(graph,rng) {
  const raw=planRun(graph,rng,'softroutes');
  const scale=2/(raw.end-1);
  const events=raw.events.map(event=>({...event,start:STAGES.flowStart+(event.start-1)*scale,duration:event.duration*scale}));
  const rootEvent=events[0];
  const rows=[{label:'execution',depth:0,parent:null,event:rootEvent,start:STAGES.flowStart,end:STAGES.flowEnd,x:644,width:246}];
  events.forEach((event,i)=>{
    const node=event.type==='node'?graph.nodes[event.id]:graph.nodes[graph.edges[event.id].to];
    const depth=event.type==='node'?1:2;
    rows.push({label:`${event.type==='edge'?'→ ':''}${String.fromCharCode(65+node.rank)}${node.lane+1}`,depth,parent:event.type==='edge'?i:0,event,start:event.start,end:event.start+event.duration+(event.type==='node'&&events[i+1]?.type==='edge'?events[i+1].duration:0),x:644+depth*16+(event.start-STAGES.flowStart)*5,width:event.type==='node'?187+rng()*17:124+rng()*19});
  });
  const particles=[];
  rows.forEach((row,rowIndex)=>{
    row.y=211+rowIndex*20;
    const count=row.depth===0?82:row.depth===1?58:45;
    for(let col=0;col<count;col++) {
      const origin=row.event.type==='node'?pill(graph.nodes[row.event.id],rng()):edgePoint(graph,graph.edges[row.event.id],rng(),'softroutes');
      particles.push({x:row.x+col/(count-1)*row.width,y:row.y,row:rowIndex,col,origin,event:row.event,departure:STAGES.flowEnd,flight:2.3+rng()*1.2,bend:(rng()-.5)*150,drift:(rng()-.5)*55});
    }
  });
  return {events,rows,particles};
}

export function stagedParticlePosition(particle,age) {
  if(age<particle.departure)return null;
  const p=ramp(age,particle.departure,particle.departure+particle.flight);
  const source=particle.origin,target=[particle.x,particle.y];
  return cubic(source,[source[0]+95+particle.drift,source[1]+particle.bend],[target[0]-105,target[1]-particle.bend*.3],target,p);
}

export function createStagedRoutes(seed=Math.floor(Math.random()*4294967296)) {
  const models=new Map();
  function model(generation) {
    if(models.has(generation))return models.get(generation);
    const rng=seededRandom(seed+Math.imul(generation,15485863));
    const previous=models.get(generation-1);
    let graph;
    do{graph=generateGraph(rng,'softroutes');}while(previous&&graph.signature===previous.graph.signature);
    const run=buildStagedRun(graph,rng);
    const ink=[];
    for(const node of graph.nodes)for(let i=0;i<38;i++)ink.push(pill(node,i/38));
    for(const edge of graph.edges)for(let i=0;i<48;i++)ink.push(edgePoint(graph,edge,i/47,'softroutes'));
    const paint=ink.map((target,i)=>({target,slot:i%4,sample:rng(),departure:STAGES.paintStart+rng()*.55+(i%4)*.1,flight:3+rng()*1.3,bend:(rng()-.5)*60}));
    const item={graph,run,ink,paint};models.set(generation,item);return item;
  }
  return (ctx,time)=>{
    const generation=Math.floor(time/STAGES.cycle),age=time%STAGES.cycle;
    for(let id=generation-4;id<=generation+1;id++)model(id);
    for(const id of models.keys())if(id<generation-4)models.delete(id);
    const current=model(generation),next=model(generation+1);
    const past=Array.from({length:4},(_,i)=>model(generation-1-i));
    const dot=(x,y,r,alpha=.85,yellow=false)=>{ctx.fillStyle=yellow?`rgba(255,219,91,${alpha})`:`rgba(80,123,255,${alpha})`;ctx.beginPath();ctx.arc(x,y,r,0,tau);ctx.fill();};
    const line=(points,alpha=.2,yellow=false,width=1)=>{ctx.strokeStyle=yellow?`rgba(255,219,91,${alpha})`:`rgba(103,139,240,${alpha})`;ctx.lineWidth=width;ctx.beginPath();points.forEach(([x,y],i)=>i?ctx.lineTo(x,y):ctx.moveTo(x,y));ctx.stroke();};
    const label=(value,x,y,alpha=.5,size=8)=>{ctx.font=`${size}px monospace`;ctx.fillStyle=`rgba(165,187,230,${alpha})`;ctx.fillText(value,x,y);};
    const opacities=[.86,.25,.075,.018,0];
    const opacity=depth=>{const low=Math.floor(depth);return mix(opacities[low],opacities[Math.min(low+1,4)],depth-low);};
    function spanFrame(item,depth,alpha,showRows=true) {
      const project=point=>spanPosition(point,depth);
      line([[566,177],[912,177],[912,484],[566,484],[566,177]].map(([x,y])=>project({x,y})),alpha*.22);
      if(!showRows)return;
      for(const row of item.run.rows) {
        const indent=584+row.depth*15;
        if(row.parent!==null) {
          const parent=item.run.rows[row.parent];
          const parentX=584+parent.depth*15;
          line([{x:parentX,y:parent.y+4},{x:parentX,y:row.y},{x:indent-4,y:row.y}].map(project),alpha*.23);
        }
        const textAt=project({x:indent+2,y:row.y+2.5});
        label(row.label,...textAt,alpha*.68,7*(1-depth*.05));
      }
    }
    function trace(item,depth,alpha) {
      spanFrame(item,depth,alpha);
      for(const p of item.run.particles)dot(...spanPosition(p,depth),p.col===0?1.7:1.15,alpha,p.col===0);
    }
    function graph(item,depth,alpha,clock,active=false) {
      const project=p=>graphPosition(p,depth);
      line([[39,171],[513,171],[513,483],[39,483],[39,171]].map(project),alpha*.13);
      const nodeEvents=new Map(item.run.events.filter(e=>e.type==='node').map(e=>[e.id,e]));
      const edgeEvents=new Map(item.run.events.filter(e=>e.type==='edge').map(e=>[e.id,e]));
      for(const edge of item.graph.edges) {
        const points=Array.from({length:45},(_,i)=>edgePoint(item.graph,edge,i/44,'softroutes'));
        line(points.map(project),alpha*.37);
        const last=points.at(-1);line([[last[0]-4,last[1]-3],last,[last[0]-4,last[1]+3]].map(project),alpha*.42);
        const event=edgeEvents.get(edge.id);
        if(active&&event&&clock>=event.start) {
          const p=clamp((clock-event.start)/event.duration);
          const selected=Array.from({length:Math.ceil(p*44)+1},(_,i)=>edgePoint(item.graph,edge,Math.min(i/44,p),'softroutes'));
          selected.push(edgePoint(item.graph,edge,p,'softroutes'));
          line(selected.map(project),alpha,true,1.8);
          if(p<1)dot(...project(edgePoint(item.graph,edge,p,'softroutes')),2.8,alpha,true);
        }
      }
      for(const node of item.graph.nodes) {
        const event=nodeEvents.get(node.id),on=active&&event&&clock>=event.start;
        const border=Array.from({length:41},(_,i)=>pill(node,i/40));
        line(border.map(project),alpha*.85,!!on,1.2);
        if(on&&clock<event.start+event.duration)dot(...project([node.x,node.y]),2.5,alpha,true);
      }
    }

    // 1. Complete the span-history movement before graph execution can start.
    const spanShift=ramp(age,0,1.35);
    for(let slot=3;slot>=0;slot--) {
      const depth=slot+spanShift;
      let alpha=opacity(depth);
      if(slot===3)alpha*=1-ramp(age,0,.7);
      if(alpha>0)trace(past[slot],depth,alpha);
    }
    const blankLayer=ramp(age,.75,1.5);
    spanFrame(current,0,blankLayer*.86,age>=STAGES.flowEnd);

    // Keep historical graph versions, rather than dissolving the old graph.
    const graphShift=ramp(age,STAGES.archiveStart,STAGES.archiveEnd);
    for(let slot=2;slot>=0;slot--) {
      const depth=slot+1+graphShift;
      const alpha=opacity(depth);
      if(alpha>0)graph(past[slot],depth,alpha,0,false);
    }
    graph(current,graphShift,opacity(graphShift),age,age>=STAGES.flowStart&&graphShift===0);

    // 2. The route consumes exactly two seconds. No particles exist in flight.
    // 3. Every sampled active node/edge releases its particles at the same time.
    for(const particle of current.run.particles) {
      const pos=stagedParticlePosition(particle,age);
      if(!pos)continue;
      const settled=age>=particle.departure+particle.flight;
      dot(...pos,particle.col===0?1.7:1.15,.86,settled&&particle.col===0);
    }

    // 4. The graph's recession finishes before evidence paints its new version.
    if(age>=STAGES.paintStart) {
      const evidence=[current,...past.slice(0,3)];
      for(const particle of next.paint) {
        if(age<particle.departure)continue;
        const tracePoints=evidence[particle.slot].run.particles;
        const point=tracePoints[Math.floor(particle.sample*tracePoints.length)];
        const source=spanPosition(point,particle.slot);
        const p=ramp(age,particle.departure,particle.departure+particle.flight);
        const target=particle.target;
        const pos=cubic(source,[520,source[1]+particle.bend],[target[0]+70,target[1]],target,p);
        dot(...pos,1.08,ramp(age,particle.departure,particle.departure+.12)*.75);
      }
      if(age>=STAGES.paintEnd)graph(next,0,ramp(age,STAGES.paintEnd,16.3)*.86,0,false);
    }

    label('GRAPH VERSIONS',189,522,.56,9);label('NESTED EXECUTION TRACES',648,522,.56,9);
    const stage=age<STAGES.flowStart?0:age<STAGES.flowEnd?1:age<STAGES.archiveStart?2:3;
    const titles=['01  PREPARE','02  EXECUTE · 2s','03  RECORD TOGETHER','04  ARCHIVE & REBUILD'];
    titles.forEach((title,i)=>{
      const x=80+i*230;
      label(title,x,556,i===stage?.9:.26,9);
      if(i===stage)line([[x,566],[x+155,566]],.8,false,1.5);
    });
  };
}

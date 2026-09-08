const tau=Math.PI*2;
const mix=(a,b,t)=>a+(b-a)*t;
const clamp=x=>Math.max(0,Math.min(x,1));
const smooth=x=>{const p=clamp(x);return p*p*(3-2*p);};
const ramp=(x,a,b)=>smooth((x-a)/(b-a));

export function seededRandom(seed) {
  let state=seed>>>0;
  return ()=>{
    state+=0x6D2B79F5;
    let n=Math.imul(state^(state>>>15),1|state);
    n^=n+Math.imul(n^(n>>>7),61|n);
    return ((n^(n>>>14))>>>0)/4294967296;
  };
}
const choose=(items,rng)=>items[Math.floor(rng()*items.length)];

export function generateGraph(rng,style) {
  const laneCount=['decisions','spanrail'].includes(style)?4:3;
  const rankCount=5+Math.floor(rng()*2);
  const nodes=[],ranks=[],edges=[];
  for(let rank=0;rank<rankCount;rank++) {
    const terminal=rank===0||rank===rankCount-1;
    const count=terminal?1:(rank===1||rank===rankCount-2?2+Math.floor(rng()*(laneCount-1)):1+Math.floor(rng()*laneCount));
    const available=Array.from({length:laneCount},(_,i)=>i);
    for(let i=available.length-1;i>0;i--){const j=Math.floor(rng()*(i+1));[available[i],available[j]]=[available[j],available[i]];}
    const lanes=terminal?[Math.floor(laneCount/2)]:available.slice(0,count).sort((a,b)=>a-b);
    ranks.push(lanes.map(lane=>{
      const id=nodes.length;
      nodes.push({id,rank,lane,x:66+rank/(rankCount-1)*415,y:laneCount===4?195+lane*88:215+lane*112});
      return id;
    }));
  }
  const add=(from,to)=>{
    if(!edges.some(e=>e.from===from&&e.to===to))edges.push({id:edges.length,from,to});
  };
  const nearest=(id,candidates)=>{
    const distance=Math.min(...candidates.map(i=>Math.abs(nodes[id].lane-nodes[i].lane)));
    return choose(candidates.filter(i=>Math.abs(nodes[id].lane-nodes[i].lane)===distance),rng);
  };
  for(let rank=0;rank<rankCount-1;rank++) {
    const left=ranks[rank],right=ranks[rank+1];
    // Every vertex has ingress and egress, so each branch eventually merges.
    for(const to of right)add(nearest(to,left),to);
    for(const from of left)if(!edges.some(e=>e.from===from))add(from,nearest(from,right));
    if(rng()<.65)add(choose(left,rng),choose(right,rng));
  }
  const pathNodes=[ranks[0][0]],pathEdges=[];
  while(pathNodes.at(-1)!==ranks.at(-1)[0]) {
    const edge=choose(edges.filter(e=>e.from===pathNodes.at(-1)),rng);
    pathEdges.push(edge.id);pathNodes.push(edge.to);
  }
  const signature=JSON.stringify([ranks.map(ids=>ids.map(id=>nodes[id].lane)),edges.map(e=>[e.from,e.to])]);
  return {nodes,edges,ranks,laneCount,pathNodes,pathEdges,signature};
}

function polylinePoint(points,p) {
  const lengths=points.slice(1).map((b,i)=>Math.hypot(b[0]-points[i][0],b[1]-points[i][1]));
  let remaining=clamp(p)*lengths.reduce((a,b)=>a+b,0);
  for(let i=0;i<lengths.length;i++) {
    if(remaining<=lengths[i]||i===lengths.length-1) {
      const u=lengths[i]?remaining/lengths[i]:0;
      return [mix(points[i][0],points[i+1][0],u),mix(points[i][1],points[i+1][1],u)];
    }
    remaining-=lengths[i];
  }
  return points.at(-1);
}
function cubic(a,b,c,d,p) {
  const q=1-p;
  return [0,1].map(i=>q*q*q*a[i]+3*q*q*p*b[i]+3*q*p*p*c[i]+p*p*p*d[i]);
}
export function edgePoint(graph,edge,p,style) {
  const a=graph.nodes[edge.from],b=graph.nodes[edge.to];
  const start=[a.x+17,a.y],end=[b.x-17,b.y];
  const middle=mix(start[0],end[0],.5+(edge.id%3-1)*.07);
  if(style==='softroutes')return cubic(start,[middle,a.y],[middle,b.y],end,p);
  return polylinePoint([start,[middle,a.y],[middle,b.y],end],p);
}
function nodePoint(graph,node,p,style) {
  const branching=graph.edges.filter(e=>e.from===node.id).length>1;
  if(style==='decisions'&&branching)return polylinePoint([[node.x,node.y-16],[node.x+17,node.y],[node.x,node.y+16],[node.x-17,node.y],[node.x,node.y-16]],p);
  if(style==='softroutes')return [node.x+Math.cos(p*tau)*16,node.y+Math.sin(p*tau)*9];
  const corners=[[12,-7,-Math.PI/2],[12,7,0],[-12,7,Math.PI/2],[-12,-7,Math.PI]];
  const outline=corners.flatMap(([x,y,a])=>Array.from({length:5},(_,i)=>[node.x+x+Math.cos(a+i/4*Math.PI/2)*4,node.y+y+Math.sin(a+i/4*Math.PI/2)*4]));
  outline.push(outline[0]);
  return polylinePoint(outline,p);
}

export function planRun(graph,rng,style) {
  const events=[];
  let start=1;
  for(let i=0;i<graph.pathNodes.length;i++) {
    events.push({type:'node',id:graph.pathNodes[i],start,duration:.65});start+=.65;
    if(i<graph.pathEdges.length){events.push({type:'edge',id:graph.pathEdges[i],start,duration:.95});start+=.95;}
  }
  const points=[];
  events.forEach((event,row)=>{
    const count=event.type==='node'?44:30;
    const indent=event.type==='node'?0:22;
    const length=event.type==='node'?200+rng()*70:110+rng()*85;
    for(let col=0;col<count;col++) {
      const u=col/(count-1);
      const emission=style==='spanrail'?Math.floor(u*5)/5:u;
      const origin=event.type==='node'?nodePoint(graph,graph.nodes[event.id],u,style):edgePoint(graph,graph.edges[event.id],emission,style);
      points.push({x:590+indent+u*length,y:211+row*22,row,col,origin,depart:event.start+emission*event.duration,event});
    }
  });
  return {events,points,end:start};
}

const historyPoint=(point,depth)=>[720+(point.x-720)*(1-depth*.05)+depth*31,336+(point.y-336)*(1-depth*.05)-depth*25];

export function createSwimlaneStudy(style,seed=Math.floor(Math.random()*4294967296)) {
  const models=new Map();
  function model(generation) {
    if(models.has(generation))return models.get(generation);
    const rng=seededRandom(seed+Math.imul(generation,15485863));
    const previous=models.get(generation-1);
    let graph;
    do{graph=generateGraph(rng,style);}while(previous&&graph.signature===previous.graph.signature);
    const run=planRun(graph,rng,style);
    const ink=[];
    for(const node of graph.nodes)for(let i=0;i<36;i++)ink.push(nodePoint(graph,node,i/36,style));
    for(const edge of graph.edges)for(let i=0;i<42;i++)ink.push(edgePoint(graph,edge,i/41,style));
    const result={graph,run,ink};models.set(generation,result);return result;
  }
  return (ctx,t)=>{
    const generation=Math.floor(t/26),age=t%26;
    for(let id=generation-4;id<=generation+1;id++)model(id);
    for(const id of models.keys())if(id<generation-4)models.delete(id);
    const current=model(generation),next=model(generation+1);
    const past=Array.from({length:4},(_,i)=>model(generation-1-i));
    const dot=(x,y,r,alpha=1,yellow=false)=>{
      ctx.fillStyle=yellow?`rgba(255,219,91,${alpha})`:`rgba(86,126,255,${alpha})`;
      ctx.beginPath();ctx.arc(x,y,r,0,tau);ctx.fill();
    };
    const line=(points,alpha,yellow=false,width=1)=>{
      ctx.strokeStyle=yellow?`rgba(255,219,91,${alpha})`:`rgba(90,126,228,${alpha})`;
      ctx.lineWidth=width;ctx.beginPath();points.forEach(([x,y],i)=>i?ctx.lineTo(x,y):ctx.moveTo(x,y));ctx.stroke();
    };
    const label=(value,x,y,alpha=.5)=>{ctx.font='9px monospace';ctx.fillStyle=`rgba(151,175,224,${alpha})`;ctx.fillText(value,x,y);};
    const outline=(depth,alpha)=>line([[570,181],[874,181],[874,478],[570,478],[570,181]].map(([x,y])=>historyPoint({x,y},depth)),alpha*.2);
    function graphInk(item,opacity,clock) {
      const {graph,run}=item;
      const inEvent=type=>new Map(run.events.filter(e=>e.type===type).map(e=>[e.id,e]));
      const nodeEvents=inEvent('node'),edgeEvents=inEvent('edge');
      for(let lane=0;lane<graph.laneCount;lane++) {
        const y=graph.laneCount===4?195+lane*88:215+lane*112;
        if(style==='decisions'){ctx.fillStyle=`rgba(83,121,217,${opacity*.028})`;ctx.fillRect(35,y-34,471,68);}
        line([[35,y+31],[507,y+31]],opacity*(style==='spanrail'?.15:.05));
        label(String(lane+1).padStart(2,'0'),21,y+3,opacity*.27);
      }
      for(const edge of graph.edges) {
        const points=Array.from({length:43},(_,i)=>edgePoint(graph,edge,i/42,style));
        line(points,opacity*.29);
        const [x,y]=points.at(-1);line([[x-4,y-3],[x,y],[x-4,y+3]],opacity*.45);
        const event=edgeEvents.get(edge.id);
        if(event&&clock>=event.start) {
          const progress=clamp((clock-event.start)/event.duration);
          const path=Array.from({length:Math.ceil(progress*42)+1},(_,i)=>edgePoint(graph,edge,Math.min(i/42,progress),style));
          path.push(edgePoint(graph,edge,progress,style));
          line(path,opacity*.86,true,style==='softroutes'?2:1.7);
          if(progress<1)dot(...edgePoint(graph,edge,progress,style),3,opacity,true);
        }
      }
      for(const node of graph.nodes) {
        const event=nodeEvents.get(node.id);
        const activated=event&&clock>=event.start;
        const border=Array.from({length:41},(_,i)=>nodePoint(graph,node,i/40,style));
        line(border,opacity*(activated?.95:.6),!!activated,1.3);
        if(activated&&clock<event.start+event.duration) {
          const wave=(clock-event.start)/event.duration;
          dot(node.x,node.y,3,opacity,true);
          const ring=Array.from({length:41},(_,i)=>[node.x+Math.cos(i/40*tau)*(20+wave*8),node.y+Math.sin(i/40*tau)*(16+wave*6)]);
          line(ring,opacity*(1-wave)*.35,true);
        }
        if(style==='spanrail')for(let row=0;row<3;row++)line([[node.x-10,node.y-5+row*5],[node.x+9-row*3,node.y-5+row*5]],opacity*.55,!!activated);
        else if(style!=='softroutes')label(`${String.fromCharCode(65+node.rank)}${node.lane+1}`,node.x-8,node.y+3,opacity*.68);
      }
    }

    const shift=ramp(age,1,12.8);
    const opacities=[.84,.34,.11,.024,0];
    for(let slot=3;slot>=0;slot--) {
      const depth=slot+shift,low=Math.floor(depth);
      let alpha=mix(opacities[low],opacities[Math.min(low+1,4)],depth-low);
      if(slot===3)alpha*=1-ramp(age,.2,1);
      if(alpha<=0)continue;
      outline(depth,alpha);
      for(const point of past[slot].run.points)dot(...historyPoint(point,depth),1.15,alpha,point.col===0);
    }
    graphInk(current,1-ramp(age,14.5,16),age);
    if(age>=1)outline(0,ramp(age,1,7)*.84);
    for(const point of current.run.points) {
      if(age<point.depart)continue;
      const flight=style==='softroutes'?2.9:2.5;
      const p=ramp(age,point.depart,point.depart+flight);
      const source=point.origin,target=[point.x,point.y];
      const curve=style==='spanrail'?0:Math.sin(point.row)*24;
      const pos=cubic(source,[source[0]+90,source[1]+curve],[target[0]-80,target[1]],target,p);
      dot(...pos,point.col===0?1.8:1.3,.84,p===1&&point.col===0);
    }
    if(age>=16.2) {
      const evidence=[current,...past.slice(0,3)];
      for(let i=0;i<next.ink.length;i++) {
        const slot=i%4;
        const points=evidence[slot].run.points;
        const source=historyPoint(points[Math.floor(i/4)%points.length],slot);
        const departure=16.2+slot*.45+(i/next.ink.length)*1.4;
        if(age<departure)continue;
        const p=ramp(age,departure,departure+3.7);
        const target=next.ink[i];
        const pos=cubic(source,[515,source[1]],[target[0]+60,target[1]],target,p);
        dot(...pos,1.05,ramp(age,departure,departure+.15)*.62);
      }
      if(age>23)graphInk(next,ramp(age,23,25),0);
    }
    label('BRANCH · SELECT · MERGE',139,528,.5);
    label('EXECUTION CHRONOLOGY',632,522,.5);
    const phase=age<1?'A NEW GRAPH':age<current.run.end?'ONE YELLOW PATH · EVERY ACTIVATION EMITS':age<14.5?'PRESERVE THE EXECUTED PATH':age<16.2?'READ THE HISTORY':'FOUR TRACES BUILD THE NEXT GRAPH';
    label(phase,290,566,.63);
  };
}

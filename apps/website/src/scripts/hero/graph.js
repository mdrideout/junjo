const tau=Math.PI*2;
const mix=(a,b,t)=>a+(b-a)*t;
const clamp=x=>Math.max(0,Math.min(x,1));

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

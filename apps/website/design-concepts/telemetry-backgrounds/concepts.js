import { createSwimlaneStudy } from './swimlane-studies.js';

const concepts = {
  loom: ['01', 'Span loom', 'Execution events settle into nested span rows.'],
  graph: ['02', 'Causal constellation', 'Activity follows branches; each connection preserves context.'],
  batch: ['03', 'Batch current', 'Application activity gathers into batches and flows into telemetry.'],
  strata: ['04', 'Trace strata', 'A landscape of executions, each retaining its own chronology.'],
  waterfall: ['05', 'Living waterfall', 'A refinement of 01: coherent arrivals, nested spans, and a readable trace.'],
  cohort: ['06', 'Collect · seal · release', 'A refinement of 03: each batch fills, holds its shape, and departs together.'],
  braid: ['07', 'Span ribbons', 'Organic streams resolve into ordered execution spans.'],
  folio: ['08', 'Trace folios', 'A trace takes shape, then joins an archive of executions.'],
  recursive: ['09', 'Evidence return', 'Execution → spans → evidence → the next execution. The same dots complete the circuit.'],
  singularity: ['10', 'Recursive singularity', 'A continuous field unfolds into spans, gathers evidence, and returns to its own source.'],
  memory: ['11', 'Persistent traces', 'Four layers, one preserved shape per execution. The fourth fades almost out of sight.'],
  tributaries: ['12', 'Archive confluence', 'Four histories contribute to one machine. It runs once, then adds its own trace.'],
  lens: ['13', 'History lens', 'One scan reads the full archive and concentrates it into the next execution.'],
  lattice: ['14', 'Inherited lattice', 'Each trace builds a different part of the next machine, one at a time.'],
  tide: ['15', 'Memory tide', 'Echoes of all four traces curl into one machine, then a new trace joins the archive.'],
  cubevortex: ['16', 'Cube into execution', 'Cube → swirling execution → spans → history builds the next cube.'],
  executinggraph: ['17', 'Graph into execution', 'Execution follows the graph. Its dots become spans; history builds the next graph.'],
  switchboard: ['18', 'Lane switchboard', 'A new flowchart each cycle. Only one forward route activates and emits telemetry.'],
  decisions: ['19', 'Decision lanes', 'Random branches and merges; one selected route through the decision graph.'],
  softroutes: ['20', 'Soft routes', 'One luminous path through a new graph, with emissions from each activated node and edge.'],
  spanrail: ['21', 'Span rails', 'Every activated node and connection sends an ordered packet to its span row.'],
};
const selected = new URLSearchParams(location.search).get('concept');
if (Object.hasOwn(concepts, selected)) {
  document.querySelector('#gallery').hidden = true;
  document.querySelector('#detail').hidden = false;
  document.querySelector('#detail-canvas').dataset.concept = selected;
  const [number, name, description] = concepts[selected];
  document.querySelector('#concept-number').textContent = number;
  document.querySelector('#concept-name').textContent = name;
  document.querySelector('#concept-description').textContent = description;
  document.querySelector('#concept-picker').value = selected;
  document.title = `${name} — Junjo motion study`;
  if(['tributaries','lens','lattice','tide','cubevortex','executinggraph','switchboard','decisions','softroutes','spanrail'].includes(selected)) {
    document.querySelector('#copy-toggle').checked=false;
    document.querySelector('.stage').classList.add('art-only');
  }
}
document.querySelector('#concept-picker').addEventListener('change', (event) => {
  location.search = `?concept=${event.target.value}`;
});
document.querySelector('#copy-toggle').addEventListener('change', (event) => {
  document.querySelector('.stage').classList.toggle('art-only', !event.target.checked);
});

const tau = Math.PI * 2;
const fract = (x) => x - Math.floor(x);
const random = (x) => fract(Math.sin(x * 127.1 + 7.7) * 43758.5453);
const mix = (a, b, t) => a + (b - a) * t;
const smooth = (t) => t * t * (3 - 2 * t);

function scene(canvas) {
  const ctx = canvas.getContext('2d');
  const kind = canvas.dataset.concept;
  const swimlaneStudy=['switchboard','decisions','softroutes','spanrail'].includes(kind)?createSwimlaneStudy(kind):null;
  let width = 0, height = 0, visible = false, frame = 0, last = 0, time = 2;
  const motion = matchMedia('(prefers-reduced-motion: reduce)');
  const dot = (x, y, radius, alpha = 1, warm = false) => {
    ctx.fillStyle = warm ? `rgba(255,181,112,${alpha})` : `rgba(73,113,255,${alpha})`;
    ctx.beginPath(); ctx.arc(x, y, radius, 0, tau); ctx.fill();
  };
  const line = (x1, y1, x2, y2, alpha = .2, warm = false) => {
    ctx.strokeStyle = warm ? `rgba(255,180,108,${alpha})` : `rgba(81,120,255,${alpha})`;
    ctx.lineWidth = 1; ctx.beginPath(); ctx.moveTo(x1, y1); ctx.lineTo(x2, y2); ctx.stroke();
  };
  const text = (value, x, y, alpha = .6) => {
    ctx.fillStyle = `rgba(151,175,224,${alpha})`; ctx.font = '10px monospace'; ctx.fillText(value, x, y);
  };
  const ring = (x, y, r, alpha) => {
    ctx.strokeStyle = `rgba(79,121,255,${alpha})`; ctx.lineWidth = 1;
    ctx.beginPath(); ctx.arc(x, y, r, 0, tau); ctx.stroke();
  };
  const bezier = (a, b, t, bend = 0) => {
    const p = smooth(t);
    return [mix(a[0], b[0], p), mix(a[1], b[1], p) + Math.sin(t * Math.PI) * bend];
  };

  function loom(t) {
    // Source particles retain their identity as they settle into span rows.
    for (let row = 0; row < 19; row++) {
      const indent = [0, 32, 64, 64, 32, 64, 96][row % 7];
      const start = 445 + indent;
      const end = 945 - random(row + 19) * 170;
      const y = 128 + row * 22;
      line(start, y, end, y, .10);
      dot(start - 12, y, 2, .45);
      for (let col = 0; col < 62; col++) {
        const p = fract(t * .07 + random(row * 79 + col) * .92);
        const target = [mix(start, end, col / 61), y];
        const angle = random(col * 9 + row) * tau;
        const source = [180 + Math.cos(angle + t * .09) * (70 + row * 4), 325 + Math.sin(angle + t * .09) * (70 + row * 5)];
        const gather = smooth(Math.min(p / .6, 1));
        const x = mix(source[0], target[0], gather);
        const py = mix(source[1], target[1], gather) + Math.sin(gather * Math.PI) * Math.sin(row) * 55;
        const fade = Math.min(p * 12, 1) * Math.min((1 - p) * 10, 1);
        dot(x, py, col % 13 === 0 ? 2 : 1.25, fade * (.3 + gather * .55), col % 37 === 0);
      }
    }
    text('EXECUTION', 113, 490, .42); text('SPAN CHRONOLOGY', 445, 98, .55);
    for (let k = 0; k < 5; k++) { const x = 445 + k * 115; line(x, 116, x, 555, .055); }
  }

  const nodes = [
    [170,330], [345,190], [345,330], [345,470],
    [545,100], [545,230], [545,355], [545,490], [545,580],
    [745,150], [745,290], [745,420], [745,550], [905,245], [905,445],
  ];
  const edges = [[0,1],[0,2],[0,3],[1,4],[1,5],[2,5],[2,6],[3,7],[3,8],[4,9],[5,9],[5,10],[6,10],[6,11],[7,11],[8,12],[9,13],[10,13],[11,14],[12,14]];
  function graph(t) {
    const moving = nodes.map(([x,y],i) => [x + Math.sin(t * .2 + i) * 8, y + Math.cos(t * .17 + i * 2) * 12]);
    for (let e = 0; e < edges.length; e++) {
      const [a,b] = edges[e].map(i => moving[i]);
      line(...a, ...b, .18);
      for (let k = 0; k < 8; k++) {
        const p = fract(t * .14 + k / 8 + e * .117);
        const head = bezier(a,b,p);
        dot(...head, k === 0 ? 2.7 : 1.4, Math.sin(p * Math.PI) * .9, k === 0 && e % 5 === 0);
        if(k === 0) for(let tail=1;tail<6;tail++) {
          const q = p - tail * .008;
          if(q > 0) dot(...bezier(a,b,q), 1.8, .4 * (1-tail/6));
        }
      }
    }
    moving.forEach(([x,y],i) => {
      const pulse = fract(t * .23 - i * .12);
      ring(x,y, 13 + pulse * 29, (1-pulse) * .3);
      ring(x,y, 12, .45); dot(x,y,3.5,.95,i===0);
      for(let k=0;k<22;k++) {
        const a=k/22*tau+t*.06;
        dot(x+Math.cos(a)*19,y+Math.sin(a)*19, .8,.38);
      }
    });
    text('ONE EXECUTION', 117, 390, .5); text('CONNECTED EVIDENCE', 679, 80, .5);
  }

  function batch(t) {
    const sources = [[125,185],[125,325],[125,465]];
    sources.forEach(([x,y],i) => {
      ring(x,y,30,.25); ring(x,y,22,.28);
      for(let j=0;j<28;j++) {
        const a=j/28*tau+t*.16;
        dot(x+Math.cos(a)*22,y+Math.sin(a)*22,1.8,.75);
      }
      dot(x,y,4,.9,true);
      text(['AGENT','WORKFLOW','EVALUATOR'][i], x-28, y+53, .48);
      for(let k=0;k<88;k++) {
        const p=fract(t*.15+k/88+i*.13);
        const dest=[490,260+random(k*13+i)*132];
        const pos=bezier([x+35,y],dest,p,(i-1)*-45);
        dot(...pos, k%9===0?2.1:1.3,Math.sin(p*Math.PI)*.85,k%19===0);
      }
    });
    // Loose particles cross a collection boundary and become moving dot matrices.
    for(let i=0;i<54;i++) dot(508,226+i*3.7,1,.35);
    text('COLLECT',466,202,.6);
    for(let packet=0;packet<4;packet++) {
      const phase=fract(t*.09+packet/4);
      const x=525+phase*480;
      const opacity=Math.min(phase*10,1)*Math.min((1-phase)*7,1);
      for(let row=0;row<12;row++) for(let col=0;col<8;col++) {
        const assemble=smooth(Math.min(phase*9,1));
        const px=x+col*7+(1-assemble)*(random(row*8+col)*55-27);
        const py=278+row*8+(1-assemble)*(random(row*13+col)*140-70)+Math.sin(phase*tau)*10;
        dot(px,py,1.7,opacity*(.5+col/16),row===0 && col<3);
      }
      line(x-5,270,x+54,270,opacity*.25);
      line(x-5,383,x+54,383,opacity*.25);
    }
    for(let lane=0;lane<3;lane++) line(530,252+lane*80,975,252+lane*80,.06);
    text('SPAN BATCHES → TELEMETRY', 654, 451, .6);
  }

  function strata(t) {
    for(let layer=0;layer<11;layer++) {
      const depth=layer/10;
      const left=290+depth*130;
      const right=970-depth*12;
      const y=145+layer*34;
      for(let row=0;row<7;row++) {
        const start=left+[0,30,65,65,30,90,90][row];
        const end=right-random(layer*7+row)*95;
        for(let col=0;col<86;col++) {
          const u=col/85;
          const x=mix(start,end,u);
          const curve=Math.sin(u*Math.PI*1.4+depth*1.8+t*.12)*34;
          const py=y+row*5.3+curve-u*48;
          const wave=fract(t*.12-depth*.17);
          const bright=Math.exp(-Math.pow((u-wave)*16,2));
          dot(x,py,1.05+depth*.35,(.15+depth*.4+bright*.4)*Math.sin(u*Math.PI)**.3,bright>.92 && row===0);
        }
      }
      dot(left-14,y+Math.sin(depth*1.8+t*.12)*34,2,.5);
    }
    text('EXECUTION / CHRONOLOGY / EVIDENCE', 425, 600, .5);
    // A few unattached signals descend gently into the field.
    for(let i=0;i<65;i++) {
      const p=fract(t*.035+random(i));
      dot(330+random(i+70)*570,40+p*510,1.2,Math.sin(p*Math.PI)*.24);
    }
  }

  function waterfall(t) {
    const offsets=[0,32,65,65,32,65];
    for(let group=0;group<3;group++) {
      const age=fract(t/15-group/3);
      const fade=Math.min((1-age)*12,1);
      const top=136+group*141;
      line(501,top,501,top+103,.16);
      text(`TRACE 0${group+1}`,515,top-20,.48);
      for(let row=0;row<6;row++) {
        const start=520+offsets[row];
        const length=[404,270,138,205,335,220][row]-group*14;
        const y=top+row*18;
        line(501,y,start-10,y,.12);
        for(let col=0;col<64;col++) {
          const u=col/63;
          const target=[start+u*length,y];
          dot(...target,.85,.13);
          const progress=(age-row*.023-col*.0015)/.23;
          if(progress<0)continue;
          const a=random(col*19+row*13+group)*tau;
          const source=[260+Math.cos(a+t*.08)*65,310+Math.sin(a+t*.08)*100];
          const p=smooth(Math.min(progress,1));
          const pos=bezier(source,target,p,Math.sin(row)*35);
          const scan=Math.exp(-Math.pow((u-fract(age*1.3))*15,2));
          dot(...pos,col===0?2.7:1.6,fade*(.6+scan*.35),col===0 || (scan>.92&&row===0));
        }
      }
    }
    for(let i=0;i<60;i++){
      const a=i/60*tau+t*.1;
      dot(260+Math.cos(a)*78,310+Math.sin(a)*115,1,.2);
    }
  }

  function cohort(t) {
    const sources=[[180,190],[180,325],[180,460]];
    sources.forEach(([x,y],i)=>{
      ring(x,y,23,.35);dot(x,y,3.5,.9,true);
      for(let j=0;j<25;j++)dot(x+Math.cos(j/tau+t*.13)*31,y+Math.sin(j/tau+t*.13)*31,1,.4);
      text(['AGENT','WORKFLOW','EVALUATOR'][i],x-25,y+51,.4);
    });
    const collector=[535,246,111,158];
    ctx.strokeStyle='rgba(104,147,255,.22)';ctx.setLineDash([3,7]);ctx.strokeRect(...collector);ctx.setLineDash([]);
    text('COLLECT',535,224,.55);
    for(let batchIndex=0;batchIndex<3;batchIndex++) {
      const age=((t+batchIndex*5)%15);
      const departure=smooth(Math.max(0,Math.min((age-6)/6,1)));
      const shift=departure*520;
      const fade=Math.min((15-age)/2,1);
      for(let i=0;i<120;i++) {
        const arrival=(age-i/120*3.5)/1.6;
        if(arrival<0)continue;
        const row=Math.floor(i/10),col=i%10;
        const target=[549+col*9+shift,261+row*11];
        const source=sources[i%3];
        const p=Math.min(arrival,1);
        const pos=bezier([source[0]+28,source[1]],target,p,Math.sin(i)*35*(1-p));
        dot(...pos,1.85,fade*(.65+col*.03),i%40===0);
      }
      if(age>5.2) {
        const seal=Math.min((age-5.2)*2,1)*fade;
        line(540+shift,252,640+shift,252,.6*seal,true);
        line(540+shift,398,640+shift,398,.32*seal);
        if(age<6.5)ring(590,325,80+(age-5.2)*22,(1-(age-5.2)/1.3)*.25);
      }
    }
    line(662,246,980,246,.06);line(662,404,980,404,.06);
    text('RELEASE →',774,441,.5);
  }

  function braid(t) {
    for(let stream=0;stream<3;stream++)for(let strand=0;strand<9;strand++) {
      const end=.84+random(stream*9+strand)*.14;
      for(let i=0;i<150;i++) {
        const u=fract(i/150+t*.058+stream*.073);
        if(u>end)continue;
        const order=smooth(Math.max(0,Math.min((u-.25)/.42,1)));
        const x=100+u*870;
        const wave=Math.sin(u*8+t*.32+stream*2.1)*110+Math.sin(u*4-t*.18)*35;
        const organicY=320+wave+strand*3;
        const spanY=167+stream*132+strand*10;
        const y=mix(organicY,spanY,order);
        const fade=Math.min(u*8,1)*Math.min((end-u)*18,1);
        const pulse=Math.exp(-Math.pow((u-fract(t*.14+stream*.3))*12,2));
        dot(x,y,1.15+order*.3,fade*(.3+order*.36+pulse*.3),strand===0&&pulse>.82);
      }
    }
    for(let row=0;row<3;row++){
      line(697,156+row*132,960,156+row*132,.1);
      text(`SPAN GROUP 0${row+1}`,707,146+row*132,.4);
    }
  }

  function folio(t) {
    const pagePoint=(u,v,depth)=>[530+u*310+depth*33,197+v*268-u*55-depth*24];
    const outline=(depth,alpha)=>{
      const corners=[[0,0],[1,0],[1,1],[0,1],[0,0]].map(([u,v])=>pagePoint(u,v,depth));
      corners.slice(1).forEach((b,i)=>line(...corners[i],...b,alpha));
    };
    for(let depth=4;depth>0;depth--) {
      outline(depth,.08);
      for(let row=0;row<11;row++)for(let col=0;col<37;col++){
        const u=.06+([0,.07,.14,.14,.07][row%5])+col/50;
        if(u>.91-random(row)*.14)continue;
        dot(...pagePoint(u,.09+row*.075,depth),1,.12+(4-depth)*.045);
      }
    }
    const age=t%12;
    const lift=smooth(Math.max(0,Math.min((age-8)/3,1)));
    const fade=Math.min((12-age)*2,1);
    outline(lift,.27*fade);
    for(let row=0;row<11;row++)for(let col=0;col<46;col++){
      const u=.06+[0,.07,.14,.14,.07][row%5]+col/60;
      if(u>.93-random(row)*.13)continue;
      const target=pagePoint(u,.09+row*.075,lift);
      const arrival=(age-row*.3-col*.019)/2.6;
      if(arrival<0)continue;
      const p=Math.min(arrival,1);
      const source=[190+random(row*67+col)*90,240+random(col*11+row)*145];
      const pos=bezier(source,target,p,Math.sin(row+col)*55*(1-p));
      dot(...pos,col===0?2.1:1.4,fade*(.52+p*.35),col===0);
    }
    for(let i=0;i<80;i++) {
      const a=random(i)*tau+t*.1;
      dot(230+Math.cos(a)*(40+random(i+90)*50),320+Math.sin(a)*80,1.1,.26);
    }
    text('EVENTS',208,455,.45);text('TRACE → EVIDENCE',635,541,.5);
  }

  const cubic=(a,b,c,d,p)=>{
    const q=1-p;
    return [0,1].map(i=>q*q*q*a[i]+3*q*q*p*b[i]+3*q*p*p*c[i]+p*p*p*d[i]);
  };

  function recursiveField(t, fluid) {
    const origin=[fluid?325:205,325];
    const core=[865,325];
    const offsets=[0,26,52,52,26,52];
    const lengths=[310,248,132,199,267,175];
    const start=fluid?480:450;
    // A shared evidence core is a visual metaphor, not an autonomous runtime.
    const halo=ctx.createRadialGradient(...core,2,...core,72);
    halo.addColorStop(0,'rgba(255,183,114,.18)');
    halo.addColorStop(.22,'rgba(89,114,255,.12)');halo.addColorStop(1,'rgba(30,60,180,0)');
    ctx.fillStyle=halo;ctx.fillRect(core[0]-72,core[1]-72,144,144);
    for(let band=0;band<7;band++)for(let k=0;k<80;k++){
      const a=k/80*tau+t*.15;
      const r=13+band*4;
      dot(core[0]+Math.cos(a)*r,core[1]+Math.sin(a)*r*.67,1,.16+band*.04,band<2);
    }
    for(let group=0;group<3;group++)for(let row=0;row<6;row++) {
      const y=145+group*131+row*17;
      const x=start+offsets[row];
      const length=lengths[row]-group*9;
      for(let guide=0;guide<55;guide++)dot(x+guide/54*length,y,.75,fluid?.085:.13);
      if(!fluid){line(start-13,y,x-7,y,.14);if(row===0)text(`TRACE 0${group+1}`,start,y-18,.4);}
      for(let col=0;col<100;col++) {
        const u=col/99;
        const seed=group*601+row*101+col;
        const angle=random(seed)*tau;
        const source=[origin[0]+Math.cos(angle)*(fluid?26:42),origin[1]+Math.sin(angle)*(fluid?55:83)];
        const target=[x+u*length,y];
        const evidence=[core[0]+Math.cos(angle)*7,core[1]+Math.sin(angle)*7];
        const phase=fract(t/(fluid?26:24)+(fluid?col/100+row*.018+group*.18:group/3-row*.018-col*.0011));
        let pos;
        let returning=false;
        if(phase<.27) {
          const p=phase/.27;
          pos=cubic(source,[source[0]+125,source[1]],[x-90,y],target,smooth(p));
        }else if(phase<.49) {
          pos=target;
        }else if(phase<.65) {
          const p=(phase-.49)/.16;
          pos=cubic(target,[target[0]+85,y],[core[0]-28,core[1]],evidence,smooth(p));
        }else {
          const p=(phase-.65)/.35;
          const upper=(group+row)%2===0;
          const spread=fluid?row*5+group*12:row*3;
          pos=cubic(evidence,[1010,upper?20-spread:625+spread],[origin[0]-175,upper?20-spread:625+spread],source,p);
          returning=true;
        }
        const warm=returning && (col%9===0 || !fluid&&col%4===0);
        dot(...pos,col%19===0?2:1.25,returning?(fluid?.45:.53):.74,warm);
      }
    }
    if(!fluid) {
      text('EXECUTION',origin[0]-31,445,.55);
      text('EVIDENCE',core[0]-26,397,.65);
      text('INFORMS THE NEXT EXECUTION',345,577,.5);
    }
  }
  function recursive(t) { recursiveField(t,false); }
  function singularity(t) { recursiveField(t,true); }

  // Trace-local coordinates are deterministic for an execution, never for its age.
  // Recession changes only the uniform scale, translation, and opacity.
  function preservedTrace(execution) {
    const points=[];
    for(let row=0;row<11;row++) {
      const indent=[0,24,48,48,24][row%5];
      const length=285-indent-random(execution*17+row)*65;
      for(let col=0;col<52;col++) {
        const x=-145+indent+col/51*length;
        points.push({x,y:-117+row*23-x*.17,row,col});
      }
    }
    return points;
  }
  function memory(t) {
    const cycle=14;
    const execution=Math.floor(t/cycle);
    const phase=fract(t/cycle);
    const recession=smooth(Math.max(0,Math.min((phase-.7)/.3,1)));
    const opacityStops=[.94,.38,.13,.028,0];
    // Four slots: the forming/current execution and its three predecessors.
    // At rollover each completed point occupies exactly its previous position.
    for(let slot=3;slot>=0;slot--) {
      const id=execution-slot;
      const depth=slot+recession;
      const low=Math.floor(depth);
      const alpha=mix(opacityStops[low],opacityStops[Math.min(low+1,4)],depth-low);
      const scale=1-depth*.045;
      const project=(x,y)=>[635+x*scale+depth*49,345+y*scale-depth*38];
      const corners=[[-164,-154],[166,-154],[166,146],[-164,146],[-164,-154]].map(([x,y])=>project(x,y-x*.17));
      corners.slice(1).forEach((b,i)=>line(...corners[i],...b,alpha*.22));
      for(const point of preservedTrace(id)) {
        const target=project(point.x,point.y);
        let pos=target;
        let fade=1;
        if(slot===0) {
          const arrival=(phase-point.row*.015-point.col*.0011)/.32;
          if(arrival<0)continue;
          const p=Math.min(arrival,1);
          const angle=random(point.row*101+point.col+id*71)*tau;
          const source=[230+Math.cos(angle)*58,335+Math.sin(angle)*85];
          pos=cubic(source,[350,source[1]],[430,target[1]],target,smooth(p));
          fade=Math.min(arrival*5,1);
        }
        dot(...pos,(point.col===0?2.2:1.4)*scale,alpha*fade,point.col===0);
      }
    }
    text('EXECUTION',195,474,.45);text('FOUR PRESERVED TRACES',556,541,.5);
  }

  const ramp=(value,start,end)=>smooth(Math.max(0,Math.min((value-start)/(end-start),1)));
  function machinePoint(mode,part,index,count) {
    const u=index/(count-1);
    let x,y;
    if(mode==='tributaries') {
      const latitude=(index%11)/10*Math.PI;
      const longitude=(part+Math.floor(index/11)/12)*Math.PI/2;
      x=Math.cos(longitude)*Math.sin(latitude)*82;
      y=Math.cos(latitude)*92+Math.sin(longitude)*Math.sin(latitude)*19;
    }else if(mode==='lens') {
      const corners=[[0,-100],[78,0],[0,100],[-78,0],[0,-100]];
      const edge=Math.min(3,Math.floor(u*4));
      const p=u*4-edge;
      const scale=1-part*.12;
      x=mix(corners[edge][0],corners[edge+1][0],p)*scale+part*5;
      y=mix(corners[edge][1],corners[edge+1][1],p)*scale-part*3;
    }else if(mode==='lattice') {
      const corners=[[-1,-1,-1],[1,-1,-1],[1,1,-1],[-1,1,-1],[-1,-1,1],[1,-1,1],[1,1,1],[-1,1,1]];
      const edges=[[0,1],[1,2],[2,3],[3,0],[4,5],[5,6],[6,7],[7,4],[0,4],[1,5],[2,6],[3,7]];
      const edge=Math.min(2,Math.floor(u*3));
      const [a,b]=edges[part*3+edge].map(i=>corners[i]);
      const p=u*3-edge;
      const v=a.map((n,i)=>mix(n,b[i],p));
      x=v[0]*58+v[2]*29;y=v[1]*62-v[2]*27;
    }else {
      const angle=u*tau;
      const tilt=(part-1.5)*.30;
      const px=Math.cos(angle)*(60+part*10),py=Math.sin(angle)*(36+part*5);
      x=px*Math.cos(tilt)-py*Math.sin(tilt);
      y=px*Math.sin(tilt)+py*Math.cos(tilt);
    }
    return [220+x,337+y];
  }

  function historyCycle(t,mode) {
    const duration=24;
    const generation=Math.floor(t/duration);
    const phase=fract(t/duration);
    const recession=ramp(phase,.46,.86);
    const opacityStops=[.9,.38,.13,.028,0];
    const project=(point,depth)=>{
      const scale=.88*(1-depth*.045);
      return [680+point.x*scale+depth*41,342+point.y*scale-depth*32];
    };
    const histories=Array.from({length:4},(_,slot)=>preservedTrace(generation-1-slot));
    const outline=(depth,alpha)=>{
      const corners=[[-164,-154],[166,-154],[166,146],[-164,146],[-164,-154]].map(([x,y])=>project({x,y:y-x*.17},depth));
      corners.slice(1).forEach((b,i)=>line(...corners[i],...b,alpha*.19));
    };
    // The oldest trace finishes contributing before it fades; only then does
    // the new trace enter. Four trace layers remain the visual maximum.
    for(let slot=3;slot>=0;slot--) {
      const depth=slot+recession;
      const lower=Math.floor(depth);
      let alpha=mix(opacityStops[lower],opacityStops[Math.min(lower+1,4)],depth-lower);
      if(slot===3)alpha*=1-ramp(phase,.35,.45);
      if(alpha<=0)continue;
      outline(depth,alpha);
      for(const point of histories[slot])dot(...project(point,depth),point.col===0?1.8:1.2,alpha,point.col===0);
    }

    const count=143;
    const machineFade=1-ramp(phase,.60,.92);
    for(let part=0;part<4;part++)for(let index=0;index<count;index++) {
      const u=index/(count-1);
      const tracePoint=histories[part][Math.round(u*(histories[part].length-1))];
      const source=project(tracePoint,part);
      const target=machinePoint(mode,part,index,count);
      let arrival;
      if(mode==='tributaries')arrival=(phase-.025-part*.035-u*.035)/.19;
      else if(mode==='lens')arrival=(phase-.025-part*.006-u*.07)/.24;
      else if(mode==='lattice')arrival=(phase-.025-part*.065-u*.012)/.085;
      else arrival=(phase-.025-part*.03)/.23;
      if(arrival<0)continue;
      const p=Math.min(arrival,1);
      let pos;
      if(mode==='tributaries') {
        const gate=[462,240+part*64];
        if(p<.55)pos=cubic(source,[source[0]-100,source[1]],[gate[0]+20,gate[1]],gate,smooth(p/.55));
        else pos=cubic(gate,[380,gate[1]],[target[0]+55,target[1]],target,smooth((p-.55)/.45));
      }else if(mode==='lens') {
        pos=cubic(source,[493,source[1]],[330,337+(source[1]-342)*.12],target,smooth(p));
      }else if(mode==='lattice') {
        pos=cubic(source,[420,source[1]],[330,target[1]],target,smooth(p));
      }else {
        // Keep the travelling echo trace-shaped for the first half of its path.
        const translated=[source[0]-380*p,source[1]+Math.sin(p*Math.PI)*35];
        const fold=ramp(p,.42,1);
        pos=[mix(translated[0],target[0],fold),mix(translated[1],target[1],fold)];
      }
      const fade=Math.min(arrival*8,1)*machineFade;
      dot(...pos,index%13===0?1.8:1.35,fade*.8,index%13===0);
      if(p<.10&&index%13===0)ring(...source,4+p*30,(1-p/.10)*.22);
    }

    if(phase>.49) {
      const fade=ramp(phase,.49,.53);
      outline(0,fade*.9);
      for(const point of preservedTrace(generation)) {
        const release=(phase-.49-point.row*.006-point.col*.00045)/.21;
        if(release<0)continue;
        const p=Math.min(release,1);
        const index=point.row*52+point.col;
        const source=machinePoint(mode,index%4,Math.floor(index/4),count);
        const target=project(point,0);
        const pos=cubic(source,[355,source[1]],[445,target[1]],target,smooth(p));
        dot(...pos,point.col===0?1.9:1.25,Math.min(release*8,1)*.9,point.col===0);
      }
    }
    text('NEXT EXECUTION',165,483,.5);
    text('TRACE HISTORY',650,523,.5);
    const phaseName=phase<.35?'HISTORY INFORMS THE MACHINE':phase<.49?'THE NEXT EXECUTION TAKES SHAPE':phase<.82?'EXECUTE → OBSERVE':'PRESERVE THE NEW TRACE';
    text(phaseName,333,580,.58);
  }
  function tributaries(t) { historyCycle(t,'tributaries'); }
  function lens(t) { historyCycle(t,'lens'); }
  function lattice(t) { historyCycle(t,'lattice'); }
  function tide(t) { historyCycle(t,'tide'); }

  function executionGraph(generation) {
    const variation=((generation%3)+3)%3;
    const nodes=[[105,337],[185,245],[185,337],[185,429],[279,278],[279,397],[370,337]];
    nodes[4][1]+=[0,18,-12][variation];
    nodes[5][1]+=[0,-14,11][variation];
    const edges=[[0,1],[0,2],[0,3],[1,4],[2,4],[2,5],[3,5],[4,6],[5,6],[[1,5],[2,6],[3,4]][variation]];
    return {nodes,edges};
  }
  function executionMachine(mode,index,generation) {
    if(mode==='cubevortex')return machinePoint('lattice',index%4,Math.floor(index/4),143);
    const {nodes,edges}=executionGraph(generation);
    if(index<140) {
      const node=nodes[Math.floor(index/20)];
      const angle=(index%20)/20*tau;
      return [node[0]+Math.cos(angle)*9,node[1]+Math.sin(angle)*9];
    }
    const edgeIndex=(index-140)%edges.length;
    const step=Math.floor((index-140)/edges.length);
    const steps=Math.floor((571-140-edgeIndex)/edges.length);
    const [a,b]=edges[edgeIndex].map(i=>nodes[i]);
    return [mix(a[0],b[0],step/steps),mix(a[1],b[1],step/steps)];
  }
  function executionSpiral(index,age) {
    const start=machinePoint('lattice',index%4,Math.floor(index/4),143);
    const angle=Math.atan2(start[1]-337,start[0]-220)+(age-1.4)*3.15+index*.033;
    const radius=23+Math.sqrt(random(index+210))*88;
    const x=Math.cos(angle)*radius;
    return [220+x,337+Math.sin(angle)*radius*.40+x*.14];
  }
  const executionTraceProject=(point,depth)=>{
    const scale=.88*(1-depth*.045);
    return [680+point.x*scale+depth*41,342+point.y*scale-depth*32];
  };
  function executingParticle(mode,index,generation,age,trace) {
    const point=trace[index];
    const target=executionTraceProject(point,0);
    const departure=4.4+point.row*.085+point.col*.009;
    const machine=executionMachine(mode,index,generation);
    if(age<departure) {
      if(mode==='executinggraph')return machine;
      const spiral=executionSpiral(index,age);
      const morph=ramp(age,1.4,3.4);
      return [mix(machine[0],spiral[0],morph),mix(machine[1],spiral[1],morph)];
    }
    const source=mode==='cubevortex'?executionSpiral(index,departure):machine;
    const p=ramp(age,departure,departure+3.2);
    return cubic(source,[source[0]+120,source[1]-24],[target[0]-100,target[1]+Math.sin(index)*16],target,p);
  }

  function machineExecution(t,mode) {
    const duration=22;
    const generation=Math.floor(t/duration);
    const age=t%duration;
    const recession=ramp(age,4.4,9.5);
    const opacityStops=[.9,.38,.13,.028,0];
    const history=Array.from({length:4},(_,slot)=>preservedTrace(generation-1-slot));
    const currentTrace=preservedTrace(generation);
    const outline=(depth,alpha)=>{
      const corners=[[-164,-154],[166,-154],[166,146],[-164,146],[-164,-154]].map(([x,y])=>executionTraceProject({x,y:y-x*.17},depth));
      corners.slice(1).forEach((b,i)=>line(...corners[i],...b,alpha*.19));
    };
    for(let slot=3;slot>=0;slot--) {
      const depth=slot+recession;
      const low=Math.floor(depth);
      let alpha=mix(opacityStops[low],opacityStops[Math.min(low+1,4)],depth-low);
      if(slot===3)alpha*=1-ramp(age,3.4,4.4);
      if(alpha<=0)continue;
      outline(depth,alpha);
      for(const point of history[slot])dot(...executionTraceProject(point,depth),1.35,alpha,point.col===0);
    }

    if(mode==='cubevortex'&&age>1.4&&age<9.1) {
      const presence=ramp(age,1.4,3.4)*(1-ramp(age,5.8,9.1));
      const halo=ctx.createRadialGradient(220,337,12,220,337,118);
      halo.addColorStop(0,`rgba(0,0,5,${presence*.96})`);
      halo.addColorStop(.19,`rgba(5,9,24,${presence*.96})`);
      halo.addColorStop(.32,`rgba(89,109,255,${presence*.18})`);
      halo.addColorStop(1,'rgba(15,31,90,0)');
      ctx.fillStyle=halo;ctx.fillRect(100,217,240,240);
    }
    if(mode==='executinggraph'&&age<5.8) {
      const {nodes,edges}=executionGraph(generation);
      const frontier=105+Math.max(0,Math.min((age-1)/3.4,1))*265;
      const remaining=1-ramp(age,4.4,5.8);
      edges.forEach(([a,b])=>line(...nodes[a],...nodes[b],.12*remaining));
      nodes.forEach(([x,y])=>{
        const activation=Math.exp(-(((x-frontier)/38)**2))*(age>1?1:0)*remaining;
        if(activation>.01){ring(x,y,14,activation*.8);ring(x,y,20,activation*.25);}
      });
    }
    if(age>4.4)outline(0,ramp(age,4.4,8.2)*.9);

    // This is the only draw of the executing particle cohort: a stable identity
    // and opacity from machine to vortex/graph execution to its exact span slot.
    for(let index=0;index<currentTrace.length;index++) {
      const point=currentTrace[index];
      const pos=executingParticle(mode,index,generation,age,currentTrace);
      let warm=point.col===0;
      if(mode==='executinggraph'&&age>=1&&age<4.4) {
        const frontier=105+(age-1)/3.4*265;
        warm=Math.abs(pos[0]-frontier)<24;
      }
      dot(...pos,1.35,.9,warm);
    }

    // Reading evidence emits a new cohort; archived traces remain in place.
    // These particles become the next cycle's executing cohort at rollover.
    if(age>=12.5) {
      const evidence=[currentTrace,history[0],history[1],history[2]];
      for(let index=0;index<572;index++) {
        const part=index%4;
        const ordinal=Math.floor(index/4);
        const sourcePoint=evidence[part][Math.round(ordinal/142*571)];
        const source=executionTraceProject(sourcePoint,part);
        const target=executionMachine(mode,index,generation+1);
        const depart=12.5+part*.8+ordinal/142*.35;
        const p=ramp(age,depart,depart+3.2);
        if(age<depart)continue;
        const pos=cubic(source,[445,source[1]],[360,target[1]],target,p);
        const born=ramp(age,depart,depart+.18);
        dot(...pos,1.35,.9*born,currentTrace[index].col===0);
      }
    }
    text(mode==='cubevortex'?'EXECUTION MACHINE':'EXECUTION GRAPH',160,491,.5);
    text('PRESERVED TRACE HISTORY',602,524,.5);
    const phase=age<1.4?'MACHINE READY':age<4.4?(mode==='cubevortex'?'CUBE → EXECUTION VORTEX':'EXECUTION FLOWS THROUGH THE GRAPH'):age<9.5?'THE SAME DOTS BECOME SPANS':age<12.5?'PRESERVE THIS EXECUTION':'THE FULL HISTORY BUILDS THE NEXT MACHINE';
    text(phase,280,566,.6);
  }
  function cubevortex(t) { machineExecution(t,'cubevortex'); }
  function executinggraph(t) { machineExecution(t,'executinggraph'); }

  function draw() {
    ctx.setTransform(canvas.width/1000,0,0,canvas.height/650,0,0);
    ctx.fillStyle='#070a12';ctx.fillRect(0,0,1000,650);
    const glow=ctx.createRadialGradient(710,330,0,710,330,520);
    glow.addColorStop(0,'#102559');glow.addColorStop(.45,'#0a1532');glow.addColorStop(1,'#070a12');
    ctx.fillStyle=glow;ctx.fillRect(0,0,1000,650);
    for(let i=0;i<110;i++) dot(random(i+150)*1000,random(i+750)*650,.65,.12+random(i)*.18);
    if(swimlaneStudy)swimlaneStudy(ctx,time);
    else ({loom,graph,batch,strata,waterfall,cohort,braid,folio,recursive,singularity,memory,tributaries,lens,lattice,tide,cubevortex,executinggraph})[kind](time);
  }
  function animate(now) {
    if(last) time+=(now-last)/1000;
    last=now;draw();frame=requestAnimationFrame(animate);
  }
  function update() {
    cancelAnimationFrame(frame);last=0;
    if(visible&&!document.hidden&&!motion.matches)frame=requestAnimationFrame(animate);
    else if(width&&height)draw();
  }
  new ResizeObserver(([entry]) => {
    width=entry.contentRect.width;height=entry.contentRect.height;
    canvas.width=Math.round(width*devicePixelRatio);canvas.height=Math.round(height*devicePixelRatio);
    if(width&&height)draw();
  }).observe(canvas);
  new IntersectionObserver(([entry]) => {visible=entry.isIntersecting;update();}).observe(canvas);
  motion.addEventListener('change',update);
  document.addEventListener('visibilitychange',update);
}
document.querySelectorAll('canvas[data-concept]').forEach(scene);

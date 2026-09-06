const concepts = {
  loom: ['01', 'Span loom', 'Execution events settle into nested span rows.'],
  graph: ['02', 'Causal constellation', 'Activity follows branches; each connection preserves context.'],
  batch: ['03', 'Batch current', 'Application activity gathers into batches and flows into telemetry.'],
  strata: ['04', 'Trace strata', 'A landscape of executions, each retaining its own chronology.'],
  waterfall: ['05', 'Living waterfall', 'A refinement of 01: coherent arrivals, nested spans, and a readable trace.'],
  cohort: ['06', 'Collect · seal · release', 'A refinement of 03: each batch fills, holds its shape, and departs together.'],
  braid: ['07', 'Span ribbons', 'Organic streams resolve into ordered execution spans.'],
  folio: ['08', 'Trace folios', 'A trace takes shape, then joins an archive of executions.'],
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

  function draw() {
    ctx.setTransform(canvas.width/1000,0,0,canvas.height/650,0,0);
    ctx.fillStyle='#070a12';ctx.fillRect(0,0,1000,650);
    const glow=ctx.createRadialGradient(710,330,0,710,330,520);
    glow.addColorStop(0,'#102559');glow.addColorStop(.45,'#0a1532');glow.addColorStop(1,'#070a12');
    ctx.fillStyle=glow;ctx.fillRect(0,0,1000,650);
    for(let i=0;i<110;i++) dot(random(i+150)*1000,random(i+750)*650,.65,.12+random(i)*.18);
    ({loom,graph,batch,strata,waterfall,cohort,braid,folio})[kind](time);
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

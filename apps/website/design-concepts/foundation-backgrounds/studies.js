import { growingLattice } from './lattices.js';
import { connectedCanopy } from './connected-canopy.js';
import { sweepingFoundation } from './sweeping-foundation.js';

const studies = {
  sweep: { number: '08', title: 'Sweeping foundation', description: 'One lattice stretches across the section and sweeps upward into a twisting canopy. Four staggered cycles refine smaller, scattered clusters: irregular openings warm, retract, reconnect with fewer nodes, and develop new connections.', tempo: 'Continuous surface · scattered pruning · four staggered cycles', growth: true },
  braid: { number: '05', title: 'Braided lattice', description: 'A stable foundation sends up three twisting lattice towers. New nodes connect as they grow, bridges link the towers, and evidence travels through the resulting network.', tempo: 'Rooted base · gradual upward growth · connected helices', growth: true },
  arbor: { number: '06', title: 'Branching lattice', description: 'One structure grows from the foundation, separates into twisting branches, and reconnects higher up. Its shape slowly evolves while the foundation remains in place.', tempo: 'Shared roots · branching growth · network connections', growth: true },
  canopy: { number: '07', title: 'Woven canopy · living mesh', description: 'The foundation and canopy share the same vertices. Ribbons lift directly out of that mesh, keep expanding and changing shape, and develop new local connections. Occasional pruning simplifies small areas while the rest of the structure stays intact.', tempo: 'Continuous roots · ongoing development · local pruning', growth: true },
  'canopy-original': { number: '07a', title: 'Woven canopy · original', description: 'Saved original: two broad lattice ribbons grow above a separate foundation and crossfade between successive generations.', tempo: 'Original canopy for comparison', growth: true },
  strata: { number: '01', title: 'Evidence strata', description: 'Quiet layers of execution history. New signals settle into the front trace while older evidence remains visible behind it. The closest match to the idea of a foundation.', tempo: 'Slow arrivals · layered blue spans · warm span starts' },
  currents: { number: '02', title: 'Branching currents', description: 'A shared signal explores different paths. Smooth, open curves give the section a sense of possibility without adding another labeled workflow diagram.', tempo: 'Flowing paths · sparse traveling highlights' },
  planes: { number: '03', title: 'Independent planes', description: 'Three distinct structures suggest the coding agent, application, and telemetry layer. Small exchanges connect them without collapsing their boundaries.', tempo: 'Stable planes · deliberate exchanges · subtle depth' },
  weave: { number: '04', title: 'Evidence weave', description: 'An open fabric of dotted signals supports the copy. Bright threads move through a stable structure, suggesting a reusable foundation across projects.', tempo: 'Continuous field · slow blue and gold currents' },
};

const selected = new URLSearchParams(location.search).get('concept');
const gallery = document.querySelector('#gallery');
const detail = document.querySelector('#detail');
if (selected && studies[selected]) {
  gallery.hidden = true;
  detail.hidden = false;
  const study = studies[selected];
  detail.classList.toggle('growth-study', Boolean(study.growth));
  detail.classList.toggle('sweep-study', selected === 'sweep');
  document.querySelector('#grow-again').hidden = !study.growth;
  document.title = `Junjo — ${study.title} / Foundation`;
  document.querySelector('#detail-canvas').dataset.concept = selected;
  document.querySelector('#concept-picker').value = selected;
  document.querySelector('#study-number').textContent = study.number;
  document.querySelector('#study-title').textContent = study.title;
  document.querySelector('#study-description').textContent = study.description;
  document.querySelector('#study-tempo').textContent = study.tempo;
}
document.querySelector('#concept-picker').addEventListener('change', event => { location.search = `?concept=${event.target.value}`; });
document.querySelector('#copy-toggle').addEventListener('change', event => { detail.classList.toggle('hide-copy', !event.target.checked); });
document.querySelector('#strength').addEventListener('input', event => {
  document.querySelector('.stage').style.setProperty('--strength', Number(event.target.value) / 100);
  document.querySelector('#strength-value').value = `${event.target.value}%`;
});

const fract = n => n - Math.floor(n);
const random = n => fract(Math.sin(n * 127.1 + 7.7) * 43758.5453);
const mix = (a, b, p) => a + (b - a) * p;
const ease = p => { const v = Math.max(0, Math.min(1, p)); return v * v * (3 - 2 * v); };
const blue = '#86b7ff', gold = '#ffd099';
const rgba = (warm, alpha) => warm ? `rgba(255,202,143,${alpha})` : `rgba(100,155,255,${alpha})`;

function sprite(color) {
  const canvas = document.createElement('canvas'); canvas.width = canvas.height = 64;
  const context = canvas.getContext('2d');
  const glow = context.createRadialGradient(32, 32, 0, 32, 32, 32);
  glow.addColorStop(0, '#fffaf0'); glow.addColorStop(.08, color); glow.addColorStop(.24, `${color}70`); glow.addColorStop(1, `${color}00`);
  context.fillStyle = glow; context.fillRect(0, 0, 64, 64); return canvas;
}
const blueGlow = sprite(blue), goldGlow = sprite(gold);
function glow(ctx, x, y, size = 9, alpha = 1, warm = false) {
  ctx.globalAlpha = alpha; ctx.drawImage(warm ? goldGlow : blueGlow, x - size, y - size, size * 2, size * 2); ctx.globalAlpha = 1;
}
function dots(ctx, points, color, radius = 1.1) {
  ctx.fillStyle = color; ctx.beginPath();
  for (const p of points) { ctx.moveTo(p.x + radius, p.y); ctx.arc(p.x, p.y, radius, 0, Math.PI * 2); }
  ctx.fill();
}
function line(ctx, points, color, width = .6) {
  ctx.beginPath(); points.forEach((p, i) => i ? ctx.lineTo(p.x, p.y) : ctx.moveTo(p.x, p.y)); ctx.strokeStyle = color; ctx.lineWidth = width; ctx.stroke();
}
function bezier(a, b, c, d, count = 110) {
  return Array.from({ length: count }, (_, i) => {
    const t = i / (count - 1), s = 1 - t;
    return { x: s ** 3 * a.x + 3 * s ** 2 * t * b.x + 3 * s * t ** 2 * c.x + t ** 3 * d.x, y: s ** 3 * a.y + 3 * s ** 2 * t * b.y + 3 * s * t ** 2 * c.y + t ** 3 * d.y };
  });
}
function onPath(points, p) {
  const index = Math.max(0, Math.min(points.length - 1, p * (points.length - 1))), i = Math.floor(index), next = points[Math.min(i + 1, points.length - 1)];
  return { x: mix(points[i].x, next.x, index - i), y: mix(points[i].y, next.y, index - i) };
}
function packet(ctx, points, progress, warm = false, alpha = 1) {
  for (let i = 5; i >= 0; i--) {
    const p = progress - i * .006; if (p < 0 || p > 1) continue;
    const point = onPath(points, p);
    glow(ctx, point.x, point.y, i ? 5 : 10, alpha * (i ? (1 - i / 6) * .22 : 1), warm);
  }
}

function strata() {
  const rows = Array.from({ length: 16 }, (_, row) => {
    const start = 770 + [0, 36, 72, 72, 108, 36, 72, 0][row % 8];
    const end = 1440 - random(row + 40) * 150;
    return Array.from({ length: Math.round((end - start) / 8) }, (_, i) => ({ x: start + i * 8, y: 80 + row * 34 - i * .7 }));
  });
  const arrivals = Array.from({ length: 54 }, (_, i) => {
    const row = rows[i % rows.length], target = row[Math.floor(random(i + 22) * row.length)];
    return { target, phase: random(i + 80), start: { x: 340 + random(i + 31) * 330, y: 35 + random(i + 51) * 580 }, warm: i % 9 === 0 };
  });
  return {
    backdrop(ctx) {
      for (let layer = 3; layer >= 0; layer--) {
        ctx.save(); ctx.translate(layer * 36, -layer * 37); ctx.translate(1080, 320); ctx.scale(1 - layer * .045, 1 - layer * .045); ctx.translate(-1080, -320);
        const alpha = [.58, .24, .11, .045][layer];
        for (const row of rows) {
          dots(ctx, row, rgba(false, alpha), layer ? 1 : 1.25);
          glow(ctx, row[0].x, row[0].y, 7, alpha * .9, true);
        }
        ctx.restore();
      }
    },
    animate(ctx, time) {
      for (const particle of arrivals) {
        const p = fract(time / 23 + particle.phase), u = ease(p / .75);
        const x = mix(particle.start.x, particle.target.x, u);
        const y = mix(particle.start.y, particle.target.y, u) + Math.sin(u * Math.PI) * 50;
        const alpha = ease(p * 8) * (1 - ease((p - .85) / .15));
        glow(ctx, x, y, particle.warm ? 8 : 5, alpha * (particle.warm ? .65 : .55), particle.warm);
      }
    },
  };
}

function currents() {
  const paths = Array.from({ length: 9 }, (_, i) => bezier(
    { x: 430, y: 338 }, { x: 940 - i * 15, y: 338 }, { x: 770, y: 15 + i * 73 }, { x: 1490, y: 15 + i * 73 }, 140,
  ));
  return {
    backdrop(ctx) {
      paths.forEach((points, i) => { line(ctx, points, rgba(false, .07)); dots(ctx, points, rgba(false, .31 + (i % 3) * .07)); });
      glow(ctx, 430, 338, 35, .22, true);
    },
    animate(ctx, time) {
      paths.forEach((points, i) => {
        const p = fract(time / 16 + i * .117), fade = ease(p * 8) * (1 - ease((p - .85) / .15));
        packet(ctx, points, p, i % 3 === 0, fade * .85);
      });
    },
  };
}

function planes() {
  const project = (x, y, z) => ({ x: 1030 + x * .9 + y * .65, y: 448 + x * .2 - y * .3 - z });
  const frames = [280, 140, 0].map(z => [[-230,-160],[230,-160],[230,160],[-230,160],[-230,-160]].map(([x,y]) => project(x,y,z)));
  const rings = [90,125,160].map(r => Array.from({ length: 100 }, (_, i) => project(Math.cos(i / 99 * Math.PI * 2) * r, Math.sin(i / 99 * Math.PI * 2) * r * .8, 280)));
  const branch = [-1, 0, 1].map(i => bezier(project(-195,0,140),project(-40,0,140),project(-30,i*120,140),project(145,i*90,140),65));
  const spans = Array.from({ length: 9 }, (_, i) => Array.from({ length: 47 - i % 3 * 5 }, (_, j) => project(-190 + (i % 3) * 25 + j * 8, -125 + i * 30, 0)));
  const transfers = [230,-180].map(x => bezier(project(x,110,280),project(x+15,110,160),project(x-15,110,80),project(x,110,0),90));
  return {
    backdrop(ctx) {
      frames.forEach((frame,i) => {
        ctx.fillStyle = `rgba(35,74,128,${.045 + i * .015})`; ctx.beginPath(); frame.forEach((p,j) => j ? ctx.lineTo(p.x,p.y) : ctx.moveTo(p.x,p.y)); ctx.fill();
        line(ctx,frame,rgba(false,.19));
        for (let j=0;j<4;j++) { const a=frame[j],b=frame[j+1]; dots(ctx,Array.from({length:50},(_,n)=>({x:mix(a.x,b.x,n/49),y:mix(a.y,b.y,n/49)})),rgba(false,.23)); }
      });
      rings.forEach((ring,i)=>dots(ctx,ring,rgba(true,.22+i*.05),1.05));
      branch.forEach(path=>{line(ctx,path,rgba(false,.09));dots(ctx,path,rgba(false,.5),1.2);});
      spans.forEach(path=>{dots(ctx,path,rgba(false,.55),1.1);glow(ctx,path[0].x,path[0].y,6,.7,true);});
      transfers.forEach(path=>line(ctx,path,rgba(false,.14)));
    },
    animate(ctx,time) {
      rings.forEach((ring,i)=>packet(ctx,ring,fract(time/28+i*.24),true,.55));
      branch.forEach((path,i)=>packet(ctx,path,fract(time/12+i*.27),false,.8));
      transfers.forEach((path,i)=>packet(ctx,path,fract(time/14+i*.5),true,.8));
      const path=spans[Math.floor(time/4)%spans.length];packet(ctx,path,fract(time/4),false,.7);
    },
  };
}

function weave() {
  const surface = (u,v) => ({x:370+u*1150+v*130,y:345+v*270+Math.sin(u*5.3+v*.9)*75-(1-u)*v*140});
  const threads = Array.from({length:23},(_,i)=>Array.from({length:145},(_,j)=>surface(j/144,i/22)));
  const cross = Array.from({length:29},(_,i)=>Array.from({length:36},(_,j)=>surface(i/28,j/35)));
  return {
    backdrop(ctx) {
      threads.forEach((path,i)=>{line(ctx,path,rgba(false,.055));dots(ctx,path,rgba(false,.16+i/70),.95);});
      cross.forEach(path=>dots(ctx,path,rgba(false,.10),.8));
    },
    animate(ctx,time) {
      [1,4,8,11,15,18,21].forEach((row,i)=>packet(ctx,threads[row],fract(time/22+i*.141),i%3===0,.7));
      [4,13,22].forEach((col,i)=>packet(ctx,cross[col],fract(time/14+i*.32),false,.6));
    },
  };
}
const renderers={strata,currents,planes,weave,
  sweep:()=>sweepingFoundation(glow),
  braid:()=>growingLattice('braid',glow),
  arbor:()=>growingLattice('arbor',glow),
  canopy:()=>connectedCanopy(glow),
  'canopy-original':()=>growingLattice('canopy',glow),
};

// Fixed foundations are cached on resize. The lattice studies animate a sparse
// mesh; the earlier studies composite fixed geometry and shared glow sprites.
class MotionStudy {
  constructor(canvas) {
    this.canvas=canvas;this.ctx=canvas.getContext('2d');this.backdrop=document.createElement('canvas');this.backCtx=this.backdrop.getContext('2d');
    this.study=renderers[canvas.dataset.concept]();this.time=this.study.growth?(canvas.closest('.thumbnail')?17:0):8;this.frame=0;this.previous=0;this.visible=false;
    this.motion=matchMedia('(prefers-reduced-motion: reduce)');
    this.update=()=>{cancelAnimationFrame(this.frame);this.previous=0;if(this.visible&&!document.hidden&&!this.motion.matches)this.frame=requestAnimationFrame(this.animate);else this.draw();};
    this.animate=now=>{if(this.previous)this.time+=(now-this.previous)/1000;this.previous=now;this.draw();this.frame=requestAnimationFrame(this.animate);};
    this.resize=new ResizeObserver(()=>this.size());this.resize.observe(canvas.parentElement);
    this.intersection=new IntersectionObserver(([entry])=>{this.visible=entry.isIntersecting;this.update();});this.intersection.observe(canvas);
    this.motion.addEventListener('change',this.update);document.addEventListener('visibilitychange',this.update);
    if(this.study.growth&&this.motion.matches)this.time=this.study.stillTime??24;
  }
  size() {
    const {width,height}=this.canvas.parentElement.getBoundingClientRect();if(!width||!height)return;
    this.width=width;this.height=height;this.dpr=devicePixelRatio;
    this.canvas.width=this.backdrop.width=Math.round(width*this.dpr);this.canvas.height=this.backdrop.height=Math.round(height*this.dpr);
    const preview=this.canvas.closest('.thumbnail');
    this.scale=preview?height/650:Math.min(height/650,Math.max(width/1000,.55));
    this.x=preview?width/2-1040*this.scale:width-1400*this.scale;this.y=this.study.growth?height-650*this.scale:(height-650*this.scale)/2;
    if(this.study.fullWidth){this.scale=height/650;this.x=0;this.y=0;this.study.resize(width/this.scale);}
    this.transform(this.backCtx);this.study.backdrop(this.backCtx);this.draw();
  }
  transform(ctx) { const scale=this.scale*this.dpr;ctx.setTransform(scale,0,0,scale,this.x*this.dpr,this.y*this.dpr); }
  draw() {
    if(!this.width)return;
    this.ctx.setTransform(1,0,0,1,0,0);this.ctx.clearRect(0,0,this.canvas.width,this.canvas.height);this.ctx.drawImage(this.backdrop,0,0);
    this.transform(this.ctx);this.study.animate(this.ctx,this.time);
  }
  destroy() {cancelAnimationFrame(this.frame);this.resize.disconnect();this.intersection.disconnect();this.motion.removeEventListener('change',this.update);document.removeEventListener('visibilitychange',this.update);}
}
const active=Array.from(document.querySelectorAll('[data-concept]')).filter(canvas=>!canvas.closest('[hidden]')).map(canvas=>new MotionStudy(canvas));
document.querySelector('#grow-again').addEventListener('click',()=>{
  const study=active.find(item=>item.canvas.id==='detail-canvas');
    if(study){study.time=study.motion.matches?(study.study.stillTime??24):0;study.previous=0;study.draw();}
});
window.addEventListener('pagehide',event=>{if(!event.persisted)active.forEach(study=>study.destroy());});

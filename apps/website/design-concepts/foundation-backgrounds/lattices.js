// Deterministic mesh topology keeps growth inexpensive: vertices move together,
// edges stay attached, and only a few evidence signals use glow sprites.
const TAU = Math.PI * 2;
const clamp = value => Math.max(0, Math.min(1, value));
const smooth = value => { const t = clamp(value); return t * t * (3 - 2 * t); };
const mix = (a, b, t) => a + (b - a) * t;
const fract = value => value - Math.floor(value);

function makeMesh(kind) {
  const nodes = [], edges = [], tracks = [], bridges = [];
  const levels = 28, sides = kind === 'canopy' ? 11 : 7;
  const groups = kind === 'canopy' ? 2 : 3;
  const rings = [];
  const edge = (a, b, bridge = false) => {
    const value = { a, b, bridge };
    edges.push(value);
    if (bridge) bridges.push(value);
  };
  for (let group = 0; group < groups; group++) {
    rings[group] = [];
    const track = [];
    for (let level = 0; level <= levels; level++) {
      // The branching study shares one trunk before it forks.
      if (kind === 'arbor' && group > 0 && level <= 8) {
        rings[group][level] = rings[0][level];
        track.push(rings[0][level][0]);
        continue;
      }
      const ring = [];
      for (let side = 0; side < sides; side++) {
        ring.push(nodes.length);
        nodes.push({ u: level / levels, v: side / (kind === 'canopy' ? sides - 1 : sides), group });
      }
      rings[group][level] = ring;
      track.push(ring[kind === 'canopy' ? 5 : 0]);
      for (let side = 0; side < sides; side++) {
        if (kind !== 'canopy' || side < sides - 1) edge(ring[side], ring[(side + 1) % sides]);
        if (level) {
          const previous = rings[group][level - 1];
          edge(previous[side], ring[side]);
          if (kind !== 'canopy' || side < sides - 1) edge(previous[side], ring[(side + 1) % sides]);
        }
      }
    }
    tracks.push(track);
  }
  for (let group = 0; group < groups - 1; group++) {
    for (const level of (kind === 'arbor' ? [16, 21, 25] : [7, 13, 19, 25])) {
      edge(rings[group][level][kind === 'canopy' ? sides - 1 : 0], rings[group + 1][level][kind === 'canopy' ? 0 : 3], true);
      edge(rings[group][level][kind === 'canopy' ? sides - 1 : 0], rings[group + 1][level + 1][kind === 'canopy' ? 0 : 3], true);
    }
  }
  return { nodes, edges, tracks, bridges };
}

function position(kind, node, time, generation) {
  const { u, v, group } = node;
  const evolution = Math.sin(generation * 1.73) * .32;
  const sway = Math.sin(time / 16 + group * .7) * u * 16;
  let x, z, height;
  if (kind === 'canopy') {
    const across = v * 2 - 1;
    const twist = u * Math.PI * 1.65 + group * 1.35 + evolution + Math.sin(time / 20) * u * .12;
    const width = 62 + Math.sin(u * Math.PI * .8) * 190;
    x = 950 + group * 210 + Math.sin(u * 3.9 + group * .8) * u * 115 + across * width * Math.cos(twist) + sway;
    z = across * width * Math.sin(twist);
    height = u * (490 + group * 55) - across * across * u * 40;
  } else if (kind === 'arbor') {
    const fork = smooth((u - .285) / .715);
    const angle = v * TAU + u * 4.8 + evolution * u + Math.sin(time / 22) * u * .14;
    const radius = 50 - Math.sin(u * Math.PI) * 23 + fork * 22;
    x = 1070 + (group - 1) * 240 * fork + Math.sin(u * 5 + evolution) * 32 * u + Math.cos(angle) * radius + sway * fork;
    z = Math.sin(angle) * radius + (group - 1) * fork * 35;
    height = u * 515 + fork * (group === 1 ? 32 : -18);
  } else {
    const angle = v * TAU + u * TAU * 1.3 + group * .8 + evolution * u + Math.sin(time / 20) * u * .18;
    const radius = 40 + Math.sin(u * Math.PI) * 24;
    x = 780 + group * 230 + Math.sin(u * 5.2 + group * 1.6 + evolution) * u * 80 + Math.cos(angle) * radius + sway;
    z = Math.sin(angle) * radius;
    height = u * (460 + group * 44);
  }
  return { x, y: 607 - height + z * .32, z, u };
}

function foundation(ctx, kind, glow) {
  ctx.save();
  ctx.translate(1040, 614); ctx.scale(1, .10);
  const halo = ctx.createRadialGradient(0, 0, 0, 0, 0, 590);
  halo.addColorStop(0, '#356bdd30'); halo.addColorStop(.55, '#1a40851b'); halo.addColorStop(1, '#14284700');
  ctx.fillStyle = halo; ctx.fillRect(-590, -590, 1180, 1180); ctx.restore();
  for (let layer = 0; layer < 3; layer++) {
    ctx.beginPath();
    const rows = Array.from({ length: 7 }, (_, row) => Array.from({ length: 37 }, (_, col) => ({
      x: 110 + col * 40 + (row % 2) * 20,
      y: 578 + row * 10 + layer * 16 + Math.sin(col / 7) * 3,
    })));
    rows.forEach((row, r) => row.forEach((p, c) => {
      if (c) { ctx.moveTo(row[c - 1].x, row[c - 1].y); ctx.lineTo(p.x, p.y); }
      if (r) { ctx.moveTo(rows[r - 1][c].x, rows[r - 1][c].y); ctx.lineTo(p.x, p.y); }
    }));
    ctx.strokeStyle = `rgba(105,159,242,${.16 - layer * .04})`; ctx.lineWidth = .6; ctx.stroke();
    ctx.beginPath();
    rows.flat().forEach(p => { ctx.moveTo(p.x + 1, p.y); ctx.arc(p.x, p.y, 1, 0, TAU); });
    ctx.fillStyle = `rgba(131,183,255,${.6 - layer * .16})`; ctx.fill();
  }
  const roots = kind === 'braid' ? [780, 1010, 1240] : kind === 'arbor' ? [1070] : [950, 1160];
  roots.forEach(x => glow(ctx, x, 607, 20, .65, true));
}

function drawStructure(ctx, mesh, points, growth, opacity, time, glow) {
  if (opacity <= 0 || growth <= 0) return;
  const buckets = Array.from({ length: 6 }, () => []);
  for (const edge of mesh.edges) {
    let a = points[edge.a], b = points[edge.b];
    if (a.u > b.u) [a, b] = [b, a];
    if (growth < a.u) continue;
    let reveal = 1;
    if (b.u > a.u) {
      const t = smooth((growth - a.u) / (b.u - a.u));
      b = { ...b, x: mix(a.x, b.x, t), y: mix(a.y, b.y, t) };
    } else reveal = smooth((growth - a.u) * 28);
    const depth = clamp(.52 + (a.z + b.z) / 380);
    const index = Math.round(clamp(depth * reveal) * 5);
    buckets[index].push({ a, b });
  }
  ctx.globalAlpha = opacity;
  buckets.forEach((edges, i) => {
    ctx.beginPath();
    edges.forEach(({ a, b }) => { ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y); });
    ctx.lineWidth = .65 + i * .055; ctx.strokeStyle = `rgba(111,170,255,${.09 + i * .075})`; ctx.stroke();
  });
  buckets.forEach((_, i) => {
    ctx.beginPath();
    points.forEach(p => {
      if (p.u >= growth || Math.round(clamp(.52 + p.z / 190) * 5) !== i) return;
      const radius = (1 + i * .14) * smooth((growth - p.u) * 32);
      ctx.moveTo(p.x + radius, p.y); ctx.arc(p.x, p.y, radius, 0, TAU);
    });
    ctx.fillStyle = `rgba(160,204,255,${.22 + i * .14})`; ctx.fill();
  });
  ctx.globalAlpha = 1;
  mesh.tracks.forEach((track, i) => {
    const head = fract(time / 13 + i * .21) * growth * (track.length - 1);
    const a = points[track[Math.floor(head)]], b = points[track[Math.min(Math.floor(head) + 1, track.length - 1)]];
    glow(ctx, mix(a.x, b.x, fract(head)), mix(a.y, b.y, fract(head)), 10, opacity * .85, true);
    if (growth < 1) {
      const tip = growth * (track.length - 1), index = Math.floor(tip);
      const p = points[track[index]], q = points[track[Math.min(index + 1, track.length - 1)]];
      glow(ctx, mix(p.x, q.x, fract(tip)), mix(p.y, q.y, fract(tip)), 14, opacity * .85, false);
    }
  });
  mesh.bridges.forEach((edge, i) => {
    if (i % 2) return;
    const a = points[edge.a], b = points[edge.b];
    if (growth < Math.max(a.u, b.u) + .04) return;
    const t = fract(time / 10 + i * .137);
    glow(ctx, mix(a.x, b.x, t), mix(a.y, b.y, t), 8, opacity * Math.sin(t * Math.PI) * .8, true);
  });
}

export function growingLattice(kind, glow) {
  const mesh = makeMesh(kind);
  return {
    growth: true,
    backdrop(ctx) { foundation(ctx, kind, glow); },
    animate(ctx, time) {
      // New structures grow for 22 seconds, then slowly evolve. Subsequent
      // growth replaces the previous mesh gently; the foundation never resets.
      const generation = Math.floor(time / 40), phase = time % 40;
      const growth = smooth(phase / 22);
      if (generation > 0) {
        const previous = mesh.nodes.map(node => position(kind, node, time, generation - 1));
        drawStructure(ctx, mesh, previous, 1, 1 - smooth(phase / 22), time, glow);
      }
      const points = mesh.nodes.map(node => position(kind, node, time, generation));
      drawStructure(ctx, mesh, points, growth, 1, time, glow);
      for (let i = 0; i < 5; i++) {
        const p = fract(time / 24 + i * .2);
        glow(ctx, 200 + p * 1250, 598 + i % 3 * 10, 8, Math.sin(p * Math.PI) * .55, i % 2 === 0);
      }
    },
  };
}

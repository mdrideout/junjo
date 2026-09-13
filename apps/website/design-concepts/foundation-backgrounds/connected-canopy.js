const TAU = Math.PI * 2;
const clamp = value => Math.max(0, Math.min(1, value));
const smooth = value => { const t = clamp(value); return t * t * (3 - 2 * t); };
const mix = (a, b, t) => a + (b - a) * t;
const between = (a, b, t) => ({ x: mix(a.x, b.x, t), y: mix(a.y, b.y, t) });

function makeCanopy() {
  const nodes = [], floorEdges = [], edges = [], patches = [], tracks = [], bridges = [];
  const floor = [], rings = [];
  const patchLocations = new Set([
    '0/8/2', '1/10/7', '0/15/6', '1/18/3', '0/21/8',
    '1/25/5', '0/12/4', '1/14/1', '0/24/3', '1/21/8',
  ]);
  for (let row = 0; row < 9; row++) {
    floor[row] = [];
    for (let col = 0; col < 61; col++) {
      floor[row].push(nodes.length);
      const z = (row - 4) * 35;
      nodes.push({ floor: true, x: 100 + col * 24, y: 620 + z * .16, z, u: 0 });
      if (col) floorEdges.push([floor[row][col - 1], floor[row][col]]);
      if (row) {
        floorEdges.push([floor[row - 1][col], floor[row][col]]);
        if (col) floorEdges.push([floor[row - 1][col - 1], floor[row][col]]);
      }
    }
  }
  const floorCount = nodes.length;
  for (let group = 0; group < 2; group++) {
    const start = 30 + group * 9;
    // These are the actual floor node IDs, not a second set of nearby points.
    rings[group] = [floor[4].slice(start, start + 11)];
    const track = floor[4].slice(start - 12, start + 6);
    for (let level = 1; level <= 32; level++) {
      const ring = [];
      for (let side = 0; side <= 10; side++) {
        ring.push(nodes.length);
        nodes.push({ group, u: level / 32, v: side / 10 });
      }
      rings[group].push(ring);
      track.push(ring[5]);
      const previous = rings[group][level - 1];
      for (let side = 0; side <= 10; side++) {
        edges.push([previous[side], ring[side]]);
        if (side === 10) continue;
        edges.push([ring[side], ring[side + 1]]);
        if (patchLocations.has(`${group}/${level}/${side}`)) {
          patches.push({ corners: [previous[side], previous[side + 1], ring[side], ring[side + 1]], group, level });
        } else edges.push([previous[side], ring[side + 1]]);
      }
    }
    tracks.push(track);
  }
  for (const level of [8, 14, 20, 26, 30]) {
    const edge = [rings[0][level][10], rings[1][level][0]];
    bridges.push(edge);
    edges.push(edge, [rings[0][level][10], rings[1][level + 1][0]]);
  }
  patches.sort((a, b) => a.level - b.level || a.group - b.group);
  return { nodes, floor, floorCount, floorEdges, edges, patches, tracks, bridges };
}

function project(node, time) {
  if (node.floor) return node;
  const { u, v, group } = node;
  const across = v * 2 - 1;
  const maturity = smooth((time - 22) / 20);
  const rooted = smooth(u / .24);
  const evolution = maturity * (
    Math.sin(time / 39 + group * .9) * .26 + Math.sin(time / 73 + u * 2) * .17
  );
  const twist = u * Math.PI * 1.65 + rooted * (group * 1.35 + evolution);
  const width = (120 + Math.sin(u * Math.PI * .82) * 145) * (1 + maturity * u * .09 * Math.sin(time / 47 + group));
  const bend = maturity * u * u * (Math.sin(time / 53 + group) * 44 + Math.sin(time / 89) * 23);
  const x = 940 + group * 216 + Math.sin(u * 3.9 + group * .8) * u * 115 + across * width * Math.cos(twist) + bend;
  const z = across * width * Math.sin(twist) + maturity * u * 22 * Math.sin(time / 31 + u * 4 + group);
  const height = u ** 1.18 * (510 + group * 50) - across * across * u * 38;
  // u=0 has exactly the floor's coordinates; the shallow first rows lift
  // smoothly out of the surface before they turn into the twisting canopy.
  return { x, y: 620 - height + z * .26, z, u };
}

function drawFloor(ctx, mesh) {
  ctx.save(); ctx.translate(1050, 621); ctx.scale(1, .085);
  const light = ctx.createRadialGradient(0, 0, 0, 0, 0, 650);
  light.addColorStop(0, '#376add28'); light.addColorStop(1, '#1c326400');
  ctx.fillStyle = light; ctx.fillRect(-650, -650, 1300, 1300); ctx.restore();
  ctx.beginPath();
  mesh.floorEdges.forEach(([a, b]) => {
    ctx.moveTo(mesh.nodes[a].x, mesh.nodes[a].y); ctx.lineTo(mesh.nodes[b].x, mesh.nodes[b].y);
  });
  ctx.lineWidth = .7; ctx.strokeStyle = 'rgba(111,170,255,.22)'; ctx.stroke();
  ctx.beginPath();
  mesh.nodes.slice(0, mesh.floorCount).forEach(p => { ctx.moveTo(p.x + 1.15, p.y); ctx.arc(p.x, p.y, 1.15, 0, TAU); });
  ctx.fillStyle = 'rgba(160,204,255,.60)'; ctx.fill();
}

function drawMesh(ctx, mesh, points, growth) {
  const buckets = Array.from({ length: 6 }, () => []);
  for (const [aId, bId] of mesh.edges) {
    let a = points[aId], b = points[bId];
    if (a.u > b.u) [a, b] = [b, a];
    if (a.u >= growth) continue;
    const born = b.u === a.u ? smooth((growth - a.u) * 32) : 1;
    if (!born) continue;
    const depth = clamp(.50 + (a.z + b.z) / 620);
    const index = Math.round(depth * 5);
    if (b.u > growth) b = between(a, b, smooth((growth - a.u) / (b.u - a.u)));
    buckets[index].push({ a, b, born });
  }
  buckets.forEach((segments, i) => {
    ctx.beginPath();
    segments.forEach(({ a, b, born }) => {
      const end = born < 1 ? between(a, b, born) : b;
      ctx.moveTo(a.x, a.y); ctx.lineTo(end.x, end.y);
    });
    ctx.lineWidth = .7 + i * .045; ctx.strokeStyle = `rgba(111,170,255,${.12 + i * .075})`; ctx.stroke();
    ctx.beginPath();
    for (let n = mesh.floorCount; n < points.length; n++) {
      const p = points[n];
      if (p.u > growth || Math.round(clamp(.5 + p.z / 310) * 5) !== i) continue;
      const radius = (1.1 + i * .12) * smooth((growth - p.u) * 32);
      ctx.moveTo(p.x + radius, p.y); ctx.arc(p.x, p.y, radius, 0, TAU);
    }
    ctx.fillStyle = `rgba(160,204,255,${.25 + i * .13})`; ctx.fill();
  });
}

function segment(ctx, a, b, alpha, warm = false) {
  if (alpha <= 0) return;
  ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y);
  ctx.lineWidth = .9;
  ctx.strokeStyle = warm ? `rgba(255,200,140,${alpha})` : `rgba(141,191,255,${alpha})`;
  ctx.stroke();
}

function developPatch(ctx, patch, points, index, growth, time, glow) {
  const corners = patch.corners.map(id => points[id]);
  if (corners.some(p => p.u > growth)) return;
  const age = time - 25 - index * 7.5;
  const cycle = age < 0 ? 0 : Math.floor(age / 90);
  const phase = age < 0 ? 0 : age % 90;
  const develop = smooth(phase / 6);
  const prune = smooth((phase - 30) / 7);
  const existing = cycle % 2 ? [1, 2] : [0, 3];
  const next = cycle % 2 ? [0, 3] : [1, 2];
  segment(ctx, corners[existing[0]], corners[existing[1]], (1 - develop) * .4);
  segment(ctx, corners[next[0]], corners[next[1]], prune * .4);
  const strength = develop * (1 - prune);
  if (!strength) return;
  const center = {
    x: corners.reduce((total, p) => total + p.x, 0) / 4,
    y: corners.reduce((total, p) => total + p.y, 0) / 4,
  };
  const pruning = phase >= 28;
  // Refine one face into four triangles. Later, remove that added node and
  // its spokes and reconnect the face with the alternate diagonal.
  corners.forEach(p => segment(ctx, p, between(p, center, strength), .5 * strength, pruning));
  glow(ctx, center.x, center.y, pruning ? 8 : 6, strength * (pruning ? .75 : .6), pruning);
  ctx.beginPath(); ctx.arc(center.x, center.y, 1.6 * strength, 0, TAU);
  ctx.fillStyle = pruning ? '#ffd09c' : '#c7e4ff'; ctx.fill();
}

function signals(ctx, mesh, points, growth, time, glow) {
  mesh.tracks.forEach((track, index) => {
    const visible = track.filter(id => points[id].u <= growth);
    if (visible.length < 2) return;
    const phase = (time / 18 + index * .43) % 1;
    const head = phase * (visible.length - 1), step = Math.floor(head);
    const p = between(points[visible[step]], points[visible[step + 1]], head - step);
    glow(ctx, p.x, p.y, 10, Math.sin(phase * Math.PI) * .9, true);
    if (growth < 1) {
      const top = track.findIndex(id => points[id].u > growth);
      if (top > 0) {
        const a = points[track[top - 1]], b = points[track[top]];
        const tip = between(a, b, smooth((growth - a.u) / (b.u - a.u)));
        glow(ctx, tip.x, tip.y, 12, .65, false);
      }
    }
  });
  mesh.bridges.forEach(([aId, bId], index) => {
    const a = points[aId], b = points[bId];
    if (Math.max(a.u, b.u) + .03 > growth) return;
    const phase = (time / 16 + index * .21) % 1;
    const p = between(a, b, phase);
    glow(ctx, p.x, p.y, 7, Math.sin(phase * Math.PI) * .6, true);
  });
}

export function connectedCanopy(glow) {
  const mesh = makeCanopy();
  return {
    growth: true,
    stillTime: 74,
    backdrop(ctx) { drawFloor(ctx, mesh); },
    animate(ctx, time) {
      // One persistent structure. It never fades away for a new generation.
      const growth = time < 22 ? .84 * smooth(time / 22) : .84 + .16 * smooth((time - 22) / 50);
      const points = mesh.nodes.map(node => project(node, time));
      drawMesh(ctx, mesh, points, growth);
      mesh.patches.forEach((patch, index) => developPatch(ctx, patch, points, index, growth, time, glow));
      signals(ctx, mesh, points, growth, time, glow);
    },
  };
}

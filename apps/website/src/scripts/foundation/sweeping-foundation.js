const TAU = Math.PI * 2;
const clamp = value => Math.max(0, Math.min(1, value));
const smooth = value => { const t = clamp(value); return t * t * (3 - 2 * t); };
const mix = (a, b, t) => a + (b - a) * t;
const columns = 85, rows = 19;
const id = (col, row) => col * rows + row;
const inside = (patch, col, row) => patch.members.has(id(col, row));

function topology() {
  const nodes = [], edges = [];
  const patches = [
    { col: 35, row: 5, cells: [[-2,-1],[-1,-1],[0,-1],[-2,0],[-1,0],[0,0],[1,0],[2,0],[-1,1],[0,1],[1,1],[0,2]] },
    { col: 47, row: 13, cells: [[-2,0],[-1,-1],[-1,0],[-1,1],[0,-2],[0,-1],[0,0],[0,1],[0,2],[1,-1],[1,0],[1,1],[2,0]] },
    { col: 60, row: 5, cells: [[-2,-1],[-1,-1],[0,-1],[-1,0],[0,0],[1,0],[2,0],[0,1],[1,1],[2,1],[1,2]] },
    { col: 73, row: 12, cells: [[-1,-2],[0,-2],[-2,-1],[-1,-1],[0,-1],[1,-1],[-2,0],[-1,0],[0,0],[1,0],[0,1],[1,1]] },
  ].map(patch => ({
    ...patch,
    members: new Set(patch.cells.map(([col,row]) => id(patch.col + col, patch.row + row))),
    dense: [], coarse: [], denseNodes: [], coarseNodes: [],
  }));
  function addEdge(a, b) {
    const n = nodes[a], m = nodes[b];
    const patch = patches.find(p => inside(p, n.col, n.row) || inside(p, m.col, m.row));
    (patch ? patch.dense : edges).push([a, b]);
  }
  for (let col = 0; col < columns; col++) for (let row = 0; row < rows; row++) {
    const patch = patches.findIndex(p => inside(p, col, row));
    nodes.push({ col, row, s: -.04 + col / (columns - 1) * 1.08, v: row / (rows - 1) * 2 - 1, patch });
    if (patch >= 0) patches[patch].denseNodes.push(id(col, row));
    if (col) addEdge(id(col - 1, row), id(col, row));
    if (row) addEdge(id(col, row - 1), id(col, row));
    if (col && row) addEdge(id(col - 1, row - 1), id(col, row));
  }
  for (const patch of patches) {
    // Follow the actual irregular boundary, not a rectangular bounding box.
    // A few spokes reconnect each opening using one retained interior node.
    const boundary = [...new Set(patch.dense.flat().filter(node => !patch.members.has(node)))];
    boundary.sort((a,b) => Math.atan2(nodes[a].row-patch.row,nodes[a].col-patch.col) - Math.atan2(nodes[b].row-patch.row,nodes[b].col-patch.col));
    const hub = id(patch.col, patch.row);
    patch.coarseNodes.push(hub);
    boundary.forEach((node,index) => { if (index % 3 === 0) patch.coarse.push([hub,node]); });
  }
  return { nodes, edges, patches };
}

function center(s, time, width) {
  const growth = smooth(time / 14);
  const development = smooth((time - 7) / 12);
  const lift = smooth((s - .20) / .26) * (1 - smooth((s - .80) / .18));
  const wave = development * (Math.sin(time * .10 + s * 6) * 67 + Math.sin(time * .063 - s * 4) * 27);
  return {
    x: s * width + lift * growth * development * Math.sin(time * .08 + s * 8) * 42,
    h: lift * growth * (320 + 55 * Math.sin(s * 5.5) + wave),
    lift, growth, development,
  };
}

function surface(time, width) {
  // Every cross-section belongs to one sheet, including the horizontal ends.
  // There is no independently drawn floor continuing under the elevated mesh.
  const sections = Array.from({ length: columns }, (_, col) => {
    const s = -.04 + col / (columns - 1) * 1.08;
    const c = center(s, time, width);
    const before = center(s - .001, time, width), after = center(s + .001, time, width);
    const dx = after.x - before.x, dh = after.h - before.h, length = Math.hypot(dx, dh);
    const twist = c.lift * c.growth * (1.3 + (s - .35) * 4.8 + c.development * Math.sin(time * .12 + s * 7) * .78);
    return { ...c, s, nx: -dh / length, nh: dx / length, twist };
  });
  const points = [];
  for (const c of sections) for (let row = 0; row < rows; row++) {
    const v = row / (rows - 1) * 2 - 1;
    const breadth = 105 + c.lift * c.growth * (120 + c.development * Math.sin(time * .08 + c.s * 5) * 26);
    const turn = Math.sin(c.twist), depth = Math.cos(c.twist);
    const offset = v * breadth;
    const z = offset * depth;
    const foldedEdge = c.growth * c.lift * v * v * Math.sin(c.s * 11 + time * .07) * 24;
    points.push({
      x: c.x + offset * turn * c.nx + z * .08,
      y: 610 - c.h - offset * turn * c.nh + z * .24 + foldedEdge,
      z,
    });
  }
  return points;
}

function patchState(time, index) {
  const age = time - 18 - [0, 8, 21, 32][index];
  if (age < 0) return { dense: 1, coarse: 0, warm: 0, developing: 0 };
  const phase = age % 48;
  if (phase < 2) return { dense: 1, coarse: 0, warm: smooth(phase / 2), developing: 0 };
  if (phase < 5) return { dense: 1 - smooth((phase - 2) / 3), coarse: 0, warm: 1, developing: 0 };
  if (phase < 8) return { dense: 0, coarse: 0, warm: 0, developing: 0 };
  if (phase < 13) return { dense: 0, coarse: smooth((phase - 8) / 5), warm: 0, developing: 1 };
  if (phase < 24) return { dense: 0, coarse: 1, warm: 0, developing: 0 };
  if (phase < 30) {
    const dense = smooth((phase - 24) / 6);
    return { dense, coarse: 1 - dense, warm: 0, developing: 1 };
  }
  return { dense: 1, coarse: 0, warm: 0, developing: 0 };
}

function drawEdges(ctx, points, edges, alpha = 1, warm = 0, developing = 0, retract = false) {
  if (alpha <= 0) return;
  const paths = Array.from({ length: 5 }, () => []);
  edges.forEach(([a, b]) => {
    const index = Math.round(clamp(.5 + (points[a].z + points[b].z) / 700) * 4);
    paths[index].push([points[a], points[b]]);
  });
  paths.forEach((path, i) => {
    ctx.beginPath();
    path.forEach(([a, b]) => {
      const progress = retract || developing ? alpha : 1;
      ctx.moveTo(a.x, a.y); ctx.lineTo(mix(a.x, b.x, progress), mix(a.y, b.y, progress));
    });
    const brightness = alpha * (.17 + i * .07 + warm * .45 + developing * .22);
    ctx.strokeStyle = `rgba(${Math.round(mix(122,255,warm))},${Math.round(mix(182,204,warm))},${Math.round(mix(255,146,warm))},${brightness})`;
    ctx.lineWidth = .8 + warm * .4; ctx.stroke();
  });
}

function drawNodes(ctx, points, ids, alpha = 1, warm = 0) {
  if (alpha <= 0) return;
  ctx.beginPath();
  ids.forEach(id => {
    const p = points[id], radius = (1.15 + clamp(.5 + p.z / 350) * .55) * alpha;
    ctx.moveTo(p.x + radius, p.y); ctx.arc(p.x, p.y, radius, 0, TAU);
  });
  ctx.fillStyle = `rgba(${Math.round(mix(162,255,warm))},${Math.round(mix(208,211,warm))},${Math.round(mix(255,149,warm))},${alpha * mix(.72,1,warm)})`; ctx.fill();
}

export function sweepingFoundation(glow) {
  const mesh = topology();
  const permanentNodes = mesh.nodes.flatMap((node, index) => node.patch < 0 ? [index] : []);
  let width = 1400;
  return {
    growth: true,
    fullWidth: true,
    stillTime: 37,
    resize(value) { width = value; },
    backdrop() {},
    animate(ctx, time) {
      const points = surface(time, width);
      const states = mesh.patches.map((_, index) => patchState(time, index));
      drawEdges(ctx, points, mesh.edges);
      drawNodes(ctx, points, permanentNodes);
      mesh.patches.forEach((patch, index) => {
        const state = states[index];
        drawEdges(ctx, points, patch.dense, state.dense, state.warm, state.developing, state.warm > 0);
        drawEdges(ctx, points, patch.coarse, state.coarse, 0, state.developing);
        drawNodes(ctx, points, patch.denseNodes, state.dense, state.warm);
        drawNodes(ctx, points, patch.coarseNodes, state.coarse);
        if (state.warm > 0 && state.dense > 0) {
          patch.denseNodes.forEach((node, n) => {
            if (n % 5) return;
            const p = points[node]; glow(ctx, p.x, p.y, 8, state.warm * state.dense * .7, true);
          });
        }
      });
      // Signals follow the very same longitudinal mesh edges from the flat
      // foundation through the bend. They disappear over a pruned region.
      for (const [i, row] of [2, 8, 15].entries()) {
        const phase = (time / 20 + i * .32) % 1;
        const step = phase * (columns - 1), col = Math.floor(step);
        const aId = id(col, row), bId = id(col + 1, row);
        const patch = mesh.nodes[aId].patch >= 0 ? mesh.nodes[aId].patch : mesh.nodes[bId].patch;
        if (patch >= 0 && states[patch].dense < .95) continue;
        const a = points[aId], b = points[bId];
        glow(ctx, mix(a.x,b.x,step-col), mix(a.y,b.y,step-col), 9, Math.sin(phase*Math.PI)*.8, true);
      }
    },
  };
}

# Foundation background studies

Standalone studies for the homepage introduction, using its approved copy.
They are outside Astro routes and public assets and are not published in the
website build. No production component imports these files.

From `apps/website`:

```sh
python3 -m http.server 4324 --bind 127.0.0.1
```

Open <http://127.0.0.1:4324/design-concepts/foundation-backgrounds/>.

## Sweeping foundation

`?concept=sweep`: **08 / Sweeping foundation** is a new concept based on the
feedback that the previous canopy still appeared to sit on a separate strip,
and that continued development and pruning were too hard to see.

One parametric sheet spans the entire canvas width, with a small bleed past
both edges. It begins horizontally; the same longitudinal rows bend upward
and twist into the canopy over 14 seconds. There is no separate static floor
under the lifted portion. The initial growth is followed by continuous changes
in lift, bend, twist, and breadth at a visibly faster pace than study 07.

Four smaller, dispersed clusters cycle independently through a warm highlight,
retraction, an open patch, reconnection with a coarser mesh, and later refinement.
Each cluster follows an irregular 11–13-node footprint rather than a rectangular
section. Its coarser connections attach to the actual boundary. The cycles start
at staggered offsets of 0, 8, 21, and 32 seconds and overlap as they repeat. The first
highlight starts after 18 seconds; the first open patch appears after 23 seconds.
These edits affect groups of cells and visibly remove interior nodes and edges.
The surrounding surface stays in place, and the whole canopy never resets.
Traveling signals follow the same mesh and stop crossing a pruned area.

`sweeping-foundation.js` owns this renderer. Its viewport sizing fills the actual
section width without changing the framing or rendering of earlier studies.
All prior concepts remain saved and selectable.

## Growing lattice studies

The second batch responds to the direction of growing upward from a persistent
foundation into twisting structures with network interconnections.

- `?concept=braid`: 05 / Braided lattice. Three twisting mesh towers rise from
  a shared base and connect through bridges at several heights.
- `?concept=arbor`: 06 / Branching lattice. A shared trunk branches into three
  twisting structures and reconnects higher up.
- `?concept=canopy`: 07 / Woven canopy · living mesh. Refined canopy with
  shared foundation vertices, continuous development, and occasional pruning.
- `?concept=canopy-original`: 07a / Woven canopy · original. The previous
  canopy is saved intact for comparison.

The first growth takes 22 seconds. Nodes and edges appear from the bottom;
there is no pre-existing template above the foundation. **Grow again** restarts
the growth for comparison.

The refined canopy keeps one continuous structure after growth. Its root rows
reuse the actual foundation node IDs, and signal paths travel from that floor
through those roots into the ribbons. The foot of each ribbon lifts gradually
out of the same triangular surface. It continues extending over the next
50 seconds, then keeps folding and changing shape without a whole-mesh reset.

Starting after 25 seconds, small faces gradually gain a center node and new
connections. They remain developed for a while, then occasionally prune that
extra node and reconnect across a different diagonal. Pruning briefly warms
the affected links, retracts them, and leaves the surrounding mesh intact.
Each area develops independently, so the network keeps changing locally.
`connected-canopy.js` owns this refinement; the previous renderer is unchanged.

The other lattice studies retain their original behavior: the next generation
grows into place while the previous one fades, and the base remains.

`lattices.js` owns deterministic vertex/edge topology and animated projection.
Fixed foundations are cached, mesh strokes are batched by depth, and only
traveling signals and growth tips use glow sprites. These are sparse meshes,
not particle simulations.

## Previous studies

All four original studies remain available.

- `?concept=strata`: Evidence strata. Dotted execution histories with quiet
  arriving signals.
- `?concept=currents`: Branching currents. Sparse packets travel through open,
  diverging curves.
- `?concept=planes`: Independent planes. Three distinct structures exchange
  signals, suggesting the coding agent, application, and telemetry layers.
- `?concept=weave`: Evidence weave. A continuous dotted surface with moving
  blue and gold threads.

Each study has a section-copy toggle and background-strength control. Turning
off the copy also removes its legibility shade. This lets reviewers inspect the
geometry, then compare it behind the actual copy. The homepage link points to
the Astro preview on port 4323.

These are visual metaphors, not architecture or benchmark diagrams. Animation
pauses when offscreen or the document is hidden. Reduced motion renders a still
composition, with the lattice already grown. No dependencies or external assets
are required.

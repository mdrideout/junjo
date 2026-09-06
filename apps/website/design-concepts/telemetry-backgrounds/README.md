# Telemetry background motion studies

Twenty-two standalone Canvas concepts for reviewing the next Junjo hero background.
These files are outside Astro's routes and public assets; they are not included
in the production website. The existing homepage is unchanged.

From `apps/website`, run:

```sh
python3 -m http.server 4323 --bind 127.0.0.1
```

Open http://127.0.0.1:4323/design-concepts/telemetry-backgrounds/.
Each card opens a full-screen study. Toggle **Hero copy** to inspect the animation
alone. Direct links use `?concept=loom`, `?concept=graph`, `?concept=batch`, or
`?concept=strata`. Caveat uses the existing locally hosted font asset.

## Selected originals and round two

The selected originals are **01 / Span loom** (`?concept=loom`) and
**03 / Batch current** (`?concept=batch`). Their rendering functions remain
unchanged. The gallery marks them as saved picks; the first round's other two
studies remain available for reference.

New studies are separate animations with their own direct links:

- **05 / Living waterfall** (`?concept=waterfall`): refines Span loom with
  coherent arrival waves, explicit parent/child indentation, and stable rows.
- **06 / Collect · seal · release** (`?concept=cohort`): refines Batch current
  so the same particles visibly arrive, occupy batch slots, and depart together.
- **07 / Span ribbons** (`?concept=braid`): organic streams straighten into
  ordered span groups, connecting the existing atmospheric style with telemetry.
- **08 / Trace folios** (`?concept=folio`): events assemble into a page of spans
  that moves into a stack of execution records.

These are alternatives for visual review, not successive replacements for the
selected originals. No concept has been applied to the production homepage.

## Round three: recursion and preserved history

All eight earlier studies were saved in local Git commit `0020b9d` before this
round began. Their animation functions are unchanged and their URLs still work.
**05 / Living waterfall** is the selected direction for this round.

- **09 / Evidence return** (`?concept=recursive`): the waterfall gains an evidence
  collection point and a visible return path. The same particles circulate from
  execution into spans, into evidence, and back to the next execution.
- **10 / Recursive singularity** (`?concept=singularity`): a more continuous,
  densely populated variation of that circuit with fewer diagram labels.
- **11 / Persistent traces** (`?concept=memory`): a trace's local point geometry
  is determined by its execution identity. Recession changes only its uniform
  scale, translation, and opacity. There are four layers total: the current
  execution plus three predecessors. Opacity falls from 94% to 38%, 13%, and
  2.8%; the final layer fades out as a new execution enters. At each rollover,
  the previous current trace becomes the next layer without changing shape.

The recursive circuit represents evidence informing subsequent application
changes. It does not imply telemetry autonomously changes an application or
that each new execution is necessarily an improvement.

The animations illustrate telemetry concepts, not exact Junjo ingestion
mechanics. Reduced-motion preferences render a static composition; animations
stop when a canvas leaves the viewport or the document is hidden.


## Round four: all history shapes the next execution

Round three was saved in local commit `0cfbb71` before adding these studies.
**11 / Persistent traces** is the selected direction. All earlier animation
functions remain unchanged.

All four new studies share a deliberate 24-second sequence: evidence from all
four preserved trace layers forms a machine on the left, the machine holds,
executes, and sends a new trace to the archive. The oldest layer contributes
before fading, then the new trace arrives. No more than four trace layers are
visible. Each layer retains execution-specific geometry as it recedes.

- **12 / Archive confluence** (`?concept=tributaries`): four narrow streams
  converge into four sections of a spherical machine.
- **13 / History lens** (`?concept=lens`): one coordinated reading wave folds
  evidence from every layer into a nested, faceted machine.
- **14 / Inherited lattice** (`?concept=lattice`): each history layer assembles
  three edges of a wireframe cube, in sequence.
- **15 / Memory tide** (`?concept=tide`): echoes retain the shape of the traces
  while travelling left, then curl into four bands of a single machine.

These four studies open without hero copy so the left-hand execution shape is
visible immediately. The existing Hero copy toggle still allows composition
review. The four-layer history is retained; moving echoes represent evidence
being read from that history, not the removal of stored traces.


## Round five: continuous machine-to-execution transitions

The first fifteen studies were preserved in local commit `299b58a` before this
round. **14 / Inherited lattice** is the selected starting point.

- **16 / Cube into execution** (`?concept=cubevortex`): one 572-dot cohort holds
  a cube, morphs directly into an elliptical execution vortex, swirls fully for
  one second, then leaves particle by particle to occupy the new trace's span
  slots. Executing particles keep a constant opacity; the cube is not faded out
  or replaced with a second moving set.
- **17 / Graph into execution** (`?concept=executinggraph`): execution advances
  through the graph as a light wave across nodes and edges. Those same dots
  stream into spans. The history subsequently builds a graph with an updated
  connection and layout for the next cycle. The routing variations are visual
  explorations, not claims of measured quality gains.

Both have a 22-second cycle: ready shape, execution, moving output, preserved
trace, and history-driven assembly. All four history layers contribute to the
next machine without removing the stored evidence. At rollover the assembled
next machine becomes the executing cohort at exactly the same coordinates,
while the completed trace retains its geometry as the newest historical layer.
Earlier studies and the production homepage are unchanged.


## Round six: randomized forward swimlane graphs

Round five was saved in local commit `9c73abf`. **17 / Graph into execution** is
this round's selected starting point. The four new studies share the graph and
execution model in `swimlane-studies.js`, with separate visual treatments:

- **18 / Lane switchboard** (`?concept=switchboard`): rounded task nodes,
  orthogonal connectors, subtle lane guides.
- **19 / Decision lanes** (`?concept=decisions`): decision diamonds, shaded
  swimlanes, explicit alternatives and merges.
- **20 / Soft routes** (`?concept=softroutes`): curved connectors and pill nodes,
  with a narrow luminous path and fine particle emissions.
- **21 / Span rails** (`?concept=spanrail`): trace-like task nodes and ordered
  packets emitted into corresponding span rows.

A new randomized graph is generated for each execution. Adjacent generations
cannot repeat the same structure. All edges advance exactly one rank from left
to right, every vertex is reachable from the source and can reach the sink,
and branch and merge points are present. One randomly selected source-to-sink
path determines all activations. Untaken nodes and edges stay blue and emit
nothing. Each selected node and edge emits its own chronology row during its
activation. Blue telemetry particles are visually distinct from the yellow
execution route.

The complete executed path becomes the new preserved trace. Four trace layers
feed assembly of the next generated graph, with the oldest layer fading before
a new trace enters. A fresh random seed is used on each page load; randomness
is stable within each run so stored trace geometry and the next graph do not
change during an animation cycle. Earlier animations are unchanged.


## 22: staged Soft routes refinement

The original 21 studies were saved in local commit `e0ad626`. **20 / Soft
routes** remains unchanged. Its refinement is **22 / Soft routes · staged**
(`?concept=stagedroutes`), implemented in `staged-soft-routes.js`.

The stages are explicit:

1. Move the span history back, leaving the front empty. No new span guides,
   lines, or markers are drawn before the execution's particles arrive.
2. Execute one selected forward path from 1.6 to 3.6 seconds: exactly two
   seconds. No telemetry particles move during this stage.
3. At 3.6 seconds all emitters release together. Origins are randomly sampled
   from every activated node and edge. Individual curves and speeds scatter
   the particles into the span rows, with all points settled by 7.1 seconds.
4. From 8.5 to 10 seconds the completed graph recedes into its version history.
   Only after that, evidence from all four span layers paints the new graph in
   front. It is ready before the next 17.5-second cycle begins.

The first version of 22 was saved in local commit `a2a723f` before its visual
refinement. It now uses 21 or 25 open span rows: a root, child node spans, and
three repeated sibling operations per node, including its selected outgoing
transition. Child bar geometry stays within its parent. Varied dot sizes and
opacity reference **01 / Span loom**. Each span starts with an orange particle
that migrates from the graph along with the rest of the row. The canvas has no
span guide lines, enclosing boxes, row labels, or stage labels.

Both columns retain four historical/front layers, fading the oldest before a
new version enters. Right-side layer opacity falls from 86% to 12%, 2.8%, and
0.4%, before each dot's individual opacity is applied. Stored geometry and dot
variation remain unchanged as versions recede. A single traversal light crosses
node interiors and selected edges continuously; visited outlines warm gradually
and cool as the graph recedes. After the next graph's incoming dots settle, they
crossfade into its matching outlines from 15.5 to 16.8 seconds, completing the
handoff before the cycle rolls over. The renderer URL includes a revision query
so the local browser does not reuse a cached module from earlier studies.

The open-span version was saved in local commit `0cd63a5` before exploring its
hero composition. **22** now opens with hero copy enabled: orange Caveat **add**,
an animated blue gradient on **Recursive Self Improvement**, and **To Your
Application** below it. That separated composition was saved in local commit
`b39444e` before returning the heading to a vertically centered overlay. The
smaller **add** sits tightly above the main line, with subtle shadows around
the lettering for legibility. The graph and spans fill the hero behind it
without the old left-side dark overlay. The two existing paragraphs retain
their exact wording in a separate section below the hero. The Hero copy toggle
still opens an unobstructed animation view. This composition applies only to
22; the earlier studies and production homepage keep their existing layout.

The centered overlay was saved in local commit `b322d0f` before expanding the
span field. Rows now extend from near the top to near the bottom of the canvas,
and longer spans continue beyond its right edge. The vertical-gradient study
was saved in `745c9c2`. Disabling that override in browser styles revealed the
original left-to-right shade, whose left edge was 96% opaque. The current
composition keeps that preferred direction at roughly 55% of its original
strength: 53% opacity on the left, 47% at 30% across, 14% at 60% across, and
transparent on the right. The gradient remains behind the lettering.

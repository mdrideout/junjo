# Telemetry background motion studies

Seventeen standalone Canvas concepts for reviewing the next Junjo hero background.
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

# Telemetry background motion studies

Eleven standalone Canvas concepts for reviewing the next Junjo hero background.
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

# Telemetry background motion studies

Eight standalone Canvas concepts for reviewing the next Junjo hero background.
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

The animations illustrate telemetry concepts, not exact Junjo ingestion
mechanics. Reduced-motion preferences render a static composition; animations
stop when a canvas leaves the viewport or the document is hidden.

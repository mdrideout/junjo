# ADR-008: Workflow Graph exploration and selection

## Status

Accepted

## Date

2026-07-15

## Context

Studio presents one Workflow execution through several coordinated surfaces:
the serialized Graph, the nested span tree, ordered Store transitions, state
projections, the span detail panel, and a deep-linkable URL. These are different
views of one execution, not independent selections.

Mermaid renders the Graph snapshot into SVG. Mermaid-generated element IDs are
renderer implementation details and changed across a transitive dependency
upgrade, breaking Graph clicks and highlighting even though Junjo's Graph and
telemetry identities were unchanged. Agent composition also means that the
nearest Junjo span is not necessarily represented in a Workflow Graph: an
Agent, model request, or Tool operation may be physically nested inside the
Workflow Node that the Graph can display.

## Decision

### One execution selection, several projections

The selected OpenTelemetry span is the primary Workflow-detail selection. An
optional Store-transition identity refines that selection when a state change
is selected. Graph, tree, state navigation, detail panel, and URL all project
that same selection.

- Selecting an executed Graph element selects its owning span, clears any
  transition selection, updates the URL, highlights and scrolls the nested
  tree, and opens that span's detail.
- Selecting a nested-tree span updates the URL and highlights the Graph element
  that represents it.
- Selecting a Store transition selects its carrier span and transition. The
  tree and Graph follow the carrier span while the state panel shows the exact
  backend-verified transition.
- Previous and next transition controls update both identities together.
- Reloading a span URL restores the same primary selection.

The frontend stores identity and resolves the current span from the loaded
trace. It does not retain a copied telemetry object as an independent source of
truth when live trace data changes.

### Graph-relative span resolution

Every rendered Graph owns one execution Graph snapshot. To highlight a
selection, Studio walks from the selected span through physical parents and
chooses the nearest span represented by that specific snapshot.

This rule produces the required composition behavior:

- a model or provider span highlights its owning Workflow Node;
- an Agent, Agent operation, model span, or Tool span inside a Node highlights
  that Node;
- a Node inside a Subflow highlights the Subflow container in the parent Graph
  and the Node in the Subflow Graph; and
- a Workflow invoked by an Agent Tool retains its own Workflow Graph and does
  not fabricate Agent nodes inside that Graph.

Agents have dynamic operation timelines and are never invented as Mermaid
Graph nodes. Workflow-to-Agent and Agent-to-Workflow composition remains
visible through real span parentage and executable navigation.

### Junjo owns rendered identity and interaction

`JunjoGraph` remains a pure conversion from a Graph snapshot to Mermaid source.
One Mermaid DOM adapter owns the renderer boundary. After Mermaid renders, the
adapter matches the known Graph node IDs from the snapshot to rendered node and
cluster elements, annotates them with Junjo-owned `data-*` identity, and builds
an explicit node-to-element index.

Feature code uses that index and Junjo-owned identity for clicks, highlighting,
subflow activation, and execution status. It never parses Mermaid-generated IDs
as domain identity. Unexecuted Graph elements remain visible but dimmed and
non-interactive. Executed failures and active Subflow containers keep their
existing visual semantics.

Mermaid is exact-version pinned. An upgrade is an interaction-boundary change,
not a routine lockfile refresh, and requires the real-renderer acceptance suite.

## Acceptance contract

| Input | Graph | Tree | State | URL |
| --- | --- | --- | --- | --- |
| Graph node click | active node | owning span | span boundary | owning span |
| Tree span click | nearest represented ancestor | active span | span boundary | active span |
| Store transition | carrier's represented ancestor | carrier span | exact transition | carrier span |
| Previous/next transition | follows carrier | follows carrier | adjacent sequence | carrier span |
| Agent/model/tool inside Node | owning Node | selected runtime span | selected span boundary | selected runtime span |
| Node inside Subflow | parent container and child node | selected Node | selected Node boundary | selected Node |

Tests must cover normal Nodes, Subflows, RunConcurrent clusters, unexecuted
nodes, failure styling, edge-label rerendering, URL restoration, and mixed
Workflow/Agent ancestry using the actual installed Mermaid renderer.

## Consequences

Renderer upgrades can change SVG structure without changing Junjo identity.
Selection behavior remains consistent across static Workflow Graphs and dynamic
Agent descendants. The adapter is deliberately small and renderer-specific;
domain matching and selection remain independently testable.

## Rejected alternatives

- Parse Mermaid IDs throughout feature code: third-party DOM IDs are not a
  stable contract.
- Treat the nearest Junjo span as the highlighted node: Agents are Junjo spans
  but are not part of a Workflow Graph snapshot.
- Add Agent nodes to Workflow Graphs: that fabricates static topology for a
  dynamic execution model.
- Keep separate Graph, tree, state, and URL selections: the surfaces would drift
  and require ambiguous synchronization rules.
- Mock the Mermaid renderer in all tests: it cannot detect integration changes
  at the boundary that previously regressed.

## Related decisions

- [Root ADR 0005: Agent and Workflow composition](../../../../docs/adr/0005-agent-workflow-composition.md)
- [Root ADR 0007: Application execution correlation and Studio resolution](../../../../docs/adr/0007-execution-correlation-and-studio-resolution.md)
- [ADR-007: Agent execution diagnostics](007-agent-execution-diagnostics.md)

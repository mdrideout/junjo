# Workflow Graph renderer boundary

`JunjoGraph` converts an execution Graph snapshot into Mermaid source. Mermaid
only lays out and renders that source. Junjo owns Graph identity, execution
matching, selection, and interaction.

Mermaid-generated SVG IDs and nesting are not stable application contracts.
Only `mermaid-dom-adapter.ts` may interpret the rendered DOM. It matches known
node IDs from the Graph snapshot, annotates elements with
`data-junjo-graph-node-id`, and returns the index used by clicks and highlights.
Feature code must not parse Mermaid IDs.

Selection is Graph-relative. Starting from the selected span, walk physical
parents until finding the nearest Node, Subflow, or RunConcurrent span
represented in the current Graph snapshot. This is what lets Agent/model/tool
spans highlight their owning Workflow Node without inventing an Agent Graph.

Mermaid is exact-version pinned. Before upgrading it:

1. inspect the rendered DOM for ordinary Nodes, Subflow nodes, and
   RunConcurrent clusters;
2. run the real-renderer tests for DOM annotation and interaction;
3. run Workflow Graph/tree/state/URL integration tests; and
4. manually verify one nested Subflow and one Agent-inside-Node execution.

The complete interaction contract is
[ADR-008](../../../docs/adr/008-workflow-graph-exploration-and-selection.md).

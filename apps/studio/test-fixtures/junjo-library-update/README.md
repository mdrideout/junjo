These fixtures lock the current Junjo transport contract for AI Studio Phase 0.

They intentionally use the backend observability API shape:

- `attributes_json` is already JSON-decoded
- `events_json` is already JSON-decoded
- `junjo.workflow.execution_graph_snapshot` remains a JSON string attribute

Update these fixtures only when the Junjo library contract changes.

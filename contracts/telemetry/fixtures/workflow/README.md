These fixtures lock telemetry contract version 1 for the current Workflow
transport behavior shared by Junjo SDKs and AI Studio.

They intentionally use the backend observability API shape:

- `attributes_json` is already JSON-decoded
- `events_json` is already JSON-decoded
- `junjo.workflow.execution_graph_snapshot` remains a JSON string attribute

They live at the platform contract boundary so all SDK producers and Studio
consumers validate the same normalized payloads. Update them only as part of an
explicit telemetry contract change.

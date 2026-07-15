These fixtures lock the active telemetry contract version 2 Workflow behavior
shared by Junjo SDKs and AI Studio. They are the Workflow half of the same
strict contract used by the Agent fixtures in the sibling directory.

They intentionally use the backend observability API shape:

- `attributes_json` is already JSON-decoded
- `events_json` is already JSON-decoded
- event `timeUnixNano` values are exact canonical decimal strings
- OTLP dropped-attribute/event/link counters are explicit loss evidence
- `junjo.workflow.execution_graph_snapshot` remains a JSON string attribute
- Workflow Store boundaries and ordered RFC 6902 transitions carry the shared
  revision and reconstructability facts used by Studio

They live at the platform contract boundary so all SDK producers and Studio
consumers validate the same normalized payloads. Update them only as part of an
explicit telemetry contract change.

CREATE TABLE spans (
  -- OpenTelemetry Standard Attributes (Keep these as-is)
  trace_id VARCHAR(32) NOT NULL,
  span_id VARCHAR(16) NOT NULL,
  parent_span_id VARCHAR(16),
  name VARCHAR,
  -- e.g., "Handle Message Workflow", "SaveMessageNode"
  kind VARCHAR,
  -- OpenTelemetry span kind (e.g., "internal")
  start_time TIMESTAMPTZ NOT NULL,
  -- Use TIMESTAMPTZ for consistency and timezone handling
  end_time TIMESTAMPTZ NOT NULL,
  -- Use TIMESTAMPTZ
  status_code VARCHAR,
  -- OpenTelemetry status code (e.g., "UNSET", "OK", "ERROR")
  status_message VARCHAR,
  -- Optional message describing the status
  attributes_json JSON,
  -- For ALL other OpenTelemetry attributes
  events_json JSON,
  -- For OpenTelemetry events (logs)
  links_json JSON,
  -- For OpenTelemetry links
  trace_flags INTEGER,
  -- OpenTelemetry trace flags
  trace_state VARCHAR,
  -- OpenTelemetry trace state
  -- Junjo-Specific Attributes (Extracted for Performance)
  service_name VARCHAR,
  -- From the resource attributes (keep this)
  workflow_id VARCHAR,
  -- From junjo.workflow_id
  node_id VARCHAR,
  -- From node.id (within a node span)
  span_type VARCHAR,
  -- "workflow" or "node" (from junjo.span_type)
  workflow_node_count INTEGER,
  -- From junjo.workflow.node.count
  -- State Machine Information (Optimized for JSON Patch)
  initial_state JSON,
  -- State *before* any changes in this span
  final_state JSON,
  -- State *after* all changes in this span
  state_patches JSON,
  -- Array of JSON Patch documents
  -- State machine data (For querying based on transitions)
  from_state VARCHAR,
  -- the state the node transitioned from
  to_state VARCHAR,
  -- the state the node transitioned to
  -- Code (Option 1: In-line, if usually small and always retrieved)
  code TEXT,
  PRIMARY KEY (trace_id, span_id)
);

-- Indexes (Essential for Performance):
CREATE INDEX idx_trace_id ON spans (trace_id);

CREATE INDEX idx_parent_span_id ON spans (parent_span_id);

CREATE INDEX idx_start_time ON spans (start_time);

CREATE INDEX idx_end_time ON spans (end_time);

CREATE INDEX idx_workflow_id ON spans (workflow_id);

CREATE INDEX idx_node_id ON spans (node_id);

CREATE INDEX idx_service_name ON spans (service_name);

CREATE INDEX idx_span_type ON spans (span_type);

CREATE INDEX idx_from_state ON spans (from_state);

CREATE INDEX idx_to_state ON spans (to_state);

-- Optional JSON indexes (add ONLY if needed, based on query patterns):
-- CREATE INDEX idx_initial_state_path ON spans ((initial_state->>'some.key'));
-- CREATE INDEX idx_final_state_path ON spans ((final_state->>'some.key'));
-- CREATE INDEX idx_state_patches_path ON spans ((state_patches->0->>'path')); -- Example
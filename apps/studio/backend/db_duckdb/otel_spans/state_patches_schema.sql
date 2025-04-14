CREATE TABLE state_patches (
  patch_id VARCHAR PRIMARY KEY,
  service_name VARCHAR NOT NULL,
  trace_id VARCHAR(32) NOT NULL,
  span_id VARCHAR(16) NOT NULL,
  workflow_id VARCHAR NOT NULL,
  node_id VARCHAR NOT NULL,
  event_time TIMESTAMPTZ NOT NULL,
  patch_json JSON NOT NULL,
  patch_store_id VARCHAR NOT NULL,
  FOREIGN KEY (trace_id, span_id) REFERENCES spans (trace_id, span_id)
);

CREATE INDEX idx_state_patches_trace_id_span_id ON state_patches (trace_id, span_id);

CREATE INDEX idx_state_patches_workflow_id ON state_patches (workflow_id);

CREATE INDEX idx_state_patches_node_id ON state_patches (node_id);

CREATE INDEX idx_state_patches_event_time ON state_patches (event_time);

-- CREATE INDEX idx_state_patches_patch ON state_patches USING GIN (patch); -- Add ONLY if needed!
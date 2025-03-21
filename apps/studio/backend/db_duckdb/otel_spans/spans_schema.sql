CREATE TABLE spans (
  -- OpenTelemetry Standard Attributes
  trace_id VARCHAR(32) NOT NULL,
  span_id VARCHAR(16) NOT NULL,
  parent_span_id VARCHAR(16),
  name VARCHAR,
  kind VARCHAR,
  start_time TIMESTAMPTZ NOT NULL,
  end_time TIMESTAMPTZ NOT NULL,
  status_code VARCHAR,
  status_message VARCHAR,
  attributes_json JSON,
  events_json JSON,
  links_json JSON,
  trace_flags INTEGER,
  trace_state VARCHAR,
  -- Junjo Fields
  junjo_service_name VARCHAR,
  junjo_id VARCHAR,
  junjo_parent_id VARCHAR,
  junjo_span_type VARCHAR,
  -- Workflow State (Workflow-level spans only)
  junjo_initial_state JSON,
  junjo_final_state JSON,
  PRIMARY KEY (trace_id, span_id)
);

-- Indexes
CREATE INDEX idx_trace_id ON spans (trace_id);

CREATE INDEX idx_parent_span_id ON spans (parent_span_id);

CREATE INDEX idx_start_time ON spans (start_time);

CREATE INDEX idx_end_time ON spans (end_time);

CREATE INDEX idx_junjo_id ON spans (junjo_id);

CREATE INDEX idx_junjo_span_type ON spans (junjo_span_type);
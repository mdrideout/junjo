WITH RECURSIVE trace_hierarchy AS (
  -- Anchor member: Get the root span(s) of the trace
  SELECT
    trace_id,
    span_id,
    parent_span_id,
    name,
    kind,
    span_type,
    start_time,
    end_time,
    status_code,
    attributes_json,
    events_json,
    workflow_id,
    node_id,
    initial_state,
    final_state,
    state_patches,
    code,
    from_state,
    to_state,
    0 AS level -- For indentation in the output
  FROM
    spans
  WHERE
    trace_id = $ 1
    AND parent_span_id IS NULL -- Use parameterized query
  UNION
  ALL -- Recursive member: Get child spans
  SELECT
    s.trace_id,
    s.span_id,
    s.parent_span_id,
    s.name,
    s.kind,
    s.span_type,
    s.start_time,
    s.end_time,
    s.status_code,
    s.attributes_json,
    s.events_json,
    s.workflow_id,
    s.node_id,
    s.initial_state,
    s.final_state,
    s.state_patches,
    s.code,
    s.from_state,
    s.to_state,
    th.level + 1
  FROM
    spans s
    JOIN trace_hierarchy th ON s.parent_span_id = th.span_id
    AND s.trace_id = th.trace_id
)
SELECT
  trace_id,
  span_id,
  name,
  kind,
  span_type,
  start_time,
  -- These are now TIMESTAMPTZ
  end_time,
  -- These are now TIMESTAMPTZ
  status_code,
  workflow_id,
  node_id,
  from_state,
  to_state,
  level,
  attributes_json,
  events_json,
  initial_state,
  final_state,
  state_patches,
  code
FROM
  trace_hierarchy
ORDER BY
  start_time;
WITH RECURSIVE workflow_lineage AS (
  -- Anchor Member: Select the *parents* of workflow spans.
  -- We start one level *above* the workflow.
  SELECT
    p.*
  FROM
    spans p
    INNER JOIN spans w ON p.span_id = w.parent_span_id
    and p.trace_id = w.trace_id
  WHERE
    w.junjo_span_type = 'workflow'
    AND w.service_name = ?
  UNION
  ALL -- Recursive Member:  Join to find the *parent* of the current span.
  SELECT
    p.*
  FROM
    spans p
    INNER JOIN workflow_lineage wl ON p.span_id = wl.parent_span_id
    and p.trace_id = wl.trace_id
) -- Final SELECT statement: Selects all spans in the lineage (excluding workflow spans).
SELECT
  *
FROM
  workflow_lineage
ORDER BY
  start_time DESC;
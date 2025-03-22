WITH RECURSIVE workflow_spans AS (
  -- Anchor Member: Select all workflow-level spans.
  SELECT
    *
  FROM
    spans
  WHERE
    junjo_span_type = 'workflow'
  UNION
  ALL -- Recursive Member: Join the spans table with the CTE itself.
  SELECT
    s.*
  FROM
    spans s
    INNER JOIN workflow_spans ws ON s.parent_span_id = ws.span_id
    and s.trace_id = ws.trace_id
) -- Final SELECT statement: Selects all columns from the recursive CTE.
SELECT
  *
FROM
  workflow_spans;
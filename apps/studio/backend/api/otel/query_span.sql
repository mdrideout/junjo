SELECT
  *
FROM
  spans
WHERE
  trace_id = ?
  AND span_id = ?;
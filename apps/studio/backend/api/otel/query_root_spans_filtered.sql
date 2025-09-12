SELECT
  *
FROM
  spans
WHERE
  service_name = ?
  AND parent_span_id IS NULL
  AND trace_id IN (
    SELECT
      trace_id
    FROM
      spans
    WHERE
      attributes_json ->> 'openinference.span.kind' = 'LLM'
  )
ORDER BY
  start_time DESC
LIMIT
  500;
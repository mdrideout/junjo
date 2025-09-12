SELECT
  *
FROM
  spans
WHERE
  service_name = ?
  AND parent_span_id IS NULL
ORDER BY
  start_time DESC
LIMIT
  500;
SELECT
  *
FROM
  spans
WHERE
  trace_id = ?
ORDER BY
  start_time DESC;
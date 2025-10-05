SELECT
  *
FROM
  spans
WHERE
  junjo_span_type = 'workflow'
  AND service_name = ?
ORDER BY
  start_time DESC;
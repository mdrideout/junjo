SELECT
  *
FROM
  spans
WHERE
  junjo_span_type = 'workflow'
ORDER BY
  start_time DESC;
-- name: GetNodeLog :one
SELECT
  *
FROM
  node_logs
WHERE
  id = ?
LIMIT
  1;

-- name: ListNodeLogs :many
SELECT
  *
FROM
  node_logs
WHERE
  exec_id = ? -- Added WHERE clause to filter by exec_id
ORDER BY
  event_time_nano ASC;

-- name: CreateNodeLog :one
INSERT INTO
  node_logs (id, exec_id, event_time_nano, type, state)
VALUES
  (?, ?, ?, ?, ?) RETURNING *;

-- name: DeleteNodeLogByExec :exec
DELETE FROM
  node_logs
WHERE
  exec_id = ?;
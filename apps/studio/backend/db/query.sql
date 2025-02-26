-- name: GetWorkflowLog :one
SELECT
  *
FROM
  workflow_logs
WHERE
  id = ?
LIMIT
  1;

-- name: ListWorkflowLogs :many
SELECT
  *
FROM
  workflow_logs
WHERE
  exec_id = ? -- Added WHERE clause to filter by exec_id
ORDER BY
  event_time_nano DESC;

-- name: CreateWorkflowLog :one
INSERT INTO
  workflow_logs (id, exec_id, name, event_time_nano, type)
VALUES
  (?, ?, ?, ?, ?) RETURNING *;

-- name: DeleteWorkflowLogByExec :exec
DELETE FROM
  workflow_logs
WHERE
  exec_id = ?;
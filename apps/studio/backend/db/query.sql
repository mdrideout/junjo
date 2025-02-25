-- name: GetWorkflow :one
SELECT
  *
FROM
  workflows
WHERE
  id = ?
LIMIT
  1;

-- name: ListWorkflows :many
SELECT
  *
FROM
  workflows
ORDER BY
  name;

-- name: CreateWorkflow :one
INSERT INTO
  workflows (id, name)
VALUES
  (?, ?) RETURNING *;

-- name: UpdateWorkflow :one
UPDATE
  workflows
set
  name = ?,
  updated_at = CURRENT_TIMESTAMP
WHERE
  id = ? RETURNING *;

-- name: DeleteWorkflow :exec
DELETE FROM
  workflows
WHERE
  id = ?;
-- name: GetWorkflowMetadataByID :one
SELECT
  *
FROM
  workflow_metadata
WHERE
  id = ?
LIMIT
  1;

-- name: GetWorkflowMetadataByExecID :one
SELECT
  *
FROM
  workflow_metadata
WHERE
  exec_id = ?
LIMIT
  1;

-- name: CreateWorkflowMetadata :one
INSERT INTO
  workflow_metadata (id, exec_id, name, structure)
VALUES
  (?, ?, ?, ?) RETURNING *;

-- name: UpdateWorkflowMetadata :one
UPDATE
  workflow_metadata
SET
  structure = ?
WHERE
  id = ? RETURNING *;

-- name: DeleteWorkflowMetadata :exec
DELETE FROM
  workflow_metadata
WHERE
  id = ?;

-- name: ListWorkflowMetadata :many
SELECT
  *
FROM
  workflow_metadata
ORDER BY
  created_at DESC;
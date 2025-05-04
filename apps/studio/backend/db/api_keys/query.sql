-- name: CreateAPIKey :one
INSERT INTO
  api_keys (key, name)
VALUES
  (?, ?) RETURNING *;

-- name: GetAPIKey :one
SELECT
  *
FROM
  api_keys
WHERE
  key = ?
LIMIT
  1;

-- name: ListAPIKeys :many
SELECT
  *
FROM
  api_keys
ORDER BY
  created_at DESC;

-- name: DeleteAPIKey :exec
DELETE FROM
  api_keys
WHERE
  key = ?;
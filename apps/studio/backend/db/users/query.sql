-- name: CreateUser :one
INSERT INTO
  users (email, password_hash)
VALUES
  (?, ?) RETURNING *;

-- name: GetUserByEmail :one
SELECT
  *
FROM
  users
WHERE
  email = ?
LIMIT
  1;

-- name: CountUsers :one
SELECT
  COUNT(*)
FROM
  users;

-- name: ListUsers :many
SELECT
  ID,
  email,
  created_at
FROM
  users
ORDER BY
  created_at DESC;

-- name: DeleteUser :exec
DELETE FROM
  users
WHERE
  id = ?;
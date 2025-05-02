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
-- name: GetPollerState :one
SELECT
  last_key
FROM
  poller_state
WHERE
  id = 1;

-- name: UpsertPollerState :exec
INSERT INTO
  poller_state (id, last_key)
VALUES
  (1, ?) ON CONFLICT(id) DO
UPDATE
SET
  last_key = excluded.last_key;
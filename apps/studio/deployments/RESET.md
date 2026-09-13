# Resetting Studio for 0.83.0

Studio 0.83.0 replaces the database migration baseline. Existing application
databases from the previous baseline cannot be upgraded in place. Fresh
installations need no reset.

The supported distributions bind a host directory into `/app/.dbdata` in both
backend and ingestion. `JUNJO_HOST_DB_DATA_PATH` selects that directory; the
default is `./.dbdata`. `docker compose down --volumes` does **not** delete this
host directory. In the VM/Caddy distribution, it deletes the separate Caddy
certificate volume instead.

## Reset procedure

1. Retain the previous release's Compose files, image versions and `.env` so
   they can be restored together with its data if necessary.
2. Run `docker compose down` from the deployment directory. Let ingestion
   complete its normal shutdown before working with application data.
3. Keep the old application-data directory intact. Create a new, empty
   directory on the storage intended for Junjo and give the containers the
   same access permissions as before. For example, if the old directory is
   `/mnt/junjo-data`, a new directory could be
   `/mnt/junjo-data/studio-0.83.0`. Do not rename or remove `/mnt/junjo-data`
   when it is the mounted disk itself.
4. Set `JUNJO_HOST_DB_DATA_PATH` in the new release's `.env` to the new absolute
   directory path. An exported shell variable overrides `.env`; remove or
   update any conflicting export. Inspect `docker compose config` and verify
   that **both** backend and ingestion bind the new host directory to
   `/app/.dbdata`.
5. Start the new release with `docker compose up -d`. Complete first-user
   setup, create new API keys and application credentials, and update clients
   to use them. Verify that new telemetry appears in Studio. Old users,
   credentials and telemetry remain in the retained directory and are not
   imported into this fresh installation.

For rollback, stop the new stack and restore the previous release's images,
configuration and original data path together. Never point the new release at
the incompatible old database. Remove retained data separately only when it is
no longer needed; do not use volume deletion as an application reset.

## Telemetry during stops

Use normal service shutdown for planned stops. Ingestion drains requests and
flushes its pending batch when shutdown completes with working storage. Forced
termination may lose the in-memory tail even after delivery was acknowledged.
Junjo accepts that telemetry tradeoff to preserve low-resource throughput and
latency. The owning decision is
[ingestion ADR-001](../ingestion/adr/001-segmented-wal-architecture.md#acknowledgement-and-termination).

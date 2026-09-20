# Resetting Studio for a breaking upgrade

Junjo does not currently preserve backward compatibility across breaking
upgrades. The telemetry contract 3 release requires a fresh Studio data store:
stop the old stack, wipe its application data or select an empty data directory,
and initialize the new SDK/Studio pair together. There is no supported in-place
conversion or import of old telemetry. Fresh installations need no reset.

The reset includes all Studio application data: SQLite databases, ingestion WAL,
and Parquet telemetry. Users, API keys, developer tokens, evaluation data, and
execution history are discarded. Do not retain selected files in the new data
directory or copy old data back after startup.

The supported distributions bind a host directory into `/app/.dbdata` in both
backend and ingestion. `JUNJO_HOST_DB_DATA_PATH` selects that directory; the
default is `./.dbdata`. `docker compose down --volumes` does **not** delete this
host directory. In the VM/Caddy distribution, it deletes the separate Caddy
certificate volume instead.

## Reset procedure

1. Stop application telemetry producers and run `docker compose down` from the
   deployment directory. Let ingestion finish shutting down before clearing data.
2. Identify the application-data directory from `JUNJO_HOST_DB_DATA_PATH` and
   `docker compose config`. Delete its contents, or select a new, empty directory
   with the same container access permissions. If the directory is a mounted
   disk, clear the application data inside it rather than removing the mount
   point. Caddy certificate data is separate and does not need resetting.
3. Set `JUNJO_HOST_DB_DATA_PATH` in the new release's `.env` to the empty
   directory. An exported shell variable overrides `.env`; remove or update any
   conflicting export. Verify with `docker compose config` that **both** backend
   and ingestion bind that empty directory to `/app/.dbdata`.
4. Start the matching new Studio release with `docker compose up -d`. Complete
   first-user setup and create new application API keys and developer tokens.
5. Upgrade applications to the matching SDK, configure the new credentials,
   and resume telemetry. Verify that new executions appear in Studio.

The existing database initialization creates the fresh schema. A data reset does
not require a compatibility migration or changes to ingestion and query paths.
Do not connect old SDK emitters to the new semantic telemetry consumer.

## Telemetry during stops

Use normal service shutdown for planned stops. Ingestion drains requests and
flushes its pending batch when shutdown completes with working storage. Forced
termination may lose the in-memory tail even after delivery was acknowledged.
Junjo accepts that telemetry tradeoff to preserve low-resource throughput and
latency. The owning decision is
[ingestion ADR-001](../ingestion/adr/001-segmented-wal-architecture.md#acknowledgement-and-termination).

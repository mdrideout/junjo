# Resetting Studio for a breaking upgrade

Junjo does not currently preserve backward compatibility across breaking
upgrades. The telemetry contract 3 release requires a fresh Studio data store:
stop the old stack, wipe its application data or select an empty data directory,
and initialize the new SDK/Studio pair together. There is no supported in-place
conversion or import of old telemetry. Fresh installations need no reset.

Upgrading from Studio 0.85.0 or earlier to a later release requires the same
reset for a second reason: a later release refuses to start on an application
database created by Studio 0.85.0 or earlier. That upgrade also changes the
deployment itself; follow
[Upgrading from Studio 0.85.0 or earlier](#upgrading-from-studio-0850-or-earlier).

The reset includes all Studio application data: SQLite databases, ingestion WAL,
and Parquet telemetry. Users, API keys, developer tokens, evaluation data, and
execution history are discarded. Do not retain selected files in the new data
directory or copy old data back after startup.

The supported distributions bind a host directory into `/app/.dbdata` in both
`junjo-ai-studio-app` and `junjo-ai-studio-ingestion`. In Studio 0.85.0 and
earlier the first of those services is `junjo-ai-studio-backend`.
`JUNJO_HOST_DB_DATA_PATH` selects that directory; the default is `./.dbdata`.
`docker compose down --volumes` does **not** delete this host directory. In the
VM/Caddy distribution, it deletes the separate Caddy certificate volume instead.

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
   conflicting export. Verify with `docker compose config` that **both**
   `junjo-ai-studio-app` and `junjo-ai-studio-ingestion` bind that empty
   directory to `/app/.dbdata`.
4. Start the matching new Studio release with `docker compose up -d`. Complete
   first-user setup and create new application API keys and developer tokens.
5. Upgrade applications to the matching SDK, configure the new credentials,
   and resume telemetry. Verify that new executions appear in Studio.

The existing database initialization creates the fresh schema. A data reset does
not require a compatibility migration or changes to ingestion and query paths.
Do not connect old SDK emitters to the new semantic telemetry consumer.

## Upgrading from Studio 0.85.0 or earlier

Releases after Studio 0.85.0 serve the web UI and the HTTP API from one
container. Besides the reset, the deployment changes in the ways below. Take
the Compose file, `.env.example`, and proxy configuration from the new
release's distribution rather than editing the earlier ones.

Run step 1 of the reset with the earlier release's Compose file. The later
file does not define the backend and frontend services, so it would leave
their containers running.

- **Two containers instead of three.** `junjo-ai-studio-app`, from the image
  `mdrideout/junjo-ai-studio-app`, replaces `junjo-ai-studio-backend` and
  `junjo-ai-studio-frontend`. Those two images receive no further releases.
  `junjo-ai-studio-ingestion` is unchanged.
- **One Studio hostname.** The web UI and the HTTP API are one origin on port
  `26154`. Route the Studio hostname to `junjo-ai-studio-app:26154`, and remove
  the `api.` hostname, its proxy route, and anything that used port `26153`.
  A host-port override for the web UI moves from `JUNJO_FRONTEND_HOST_PORT` to
  `JUNJO_BACKEND_HOST_PORT`. Point `JUNJO_AI_STUDIO_BACKEND_BASE_URL` in SDK
  and CLI environments at the Studio hostname. The ingestion hostname is
  unchanged.
- **Six settings are removed.** Delete `JUNJO_SESSION_SECRET`,
  `JUNJO_SECURE_COOKIE_KEY`, `JUNJO_PROD_FRONTEND_URL`,
  `JUNJO_PROD_BACKEND_URL`, and `JUNJO_ALLOW_ORIGINS` from `.env`, and
  `RUN_MIGRATIONS` from a Compose file of your own. The new release's
  `.env.example` lists the settings that remain.
- **Everyone signs in again.** Accounts are created again from step 4, and a
  browser session from the earlier release is not accepted.

## Telemetry during stops

Use normal service shutdown for planned stops. Ingestion drains requests and
flushes its pending batch when shutdown completes with working storage. Forced
termination may lose the in-memory tail even after delivery was acknowledged.
Junjo accepts that telemetry tradeoff to preserve low-resource throughput and
latency. The owning decision is
[ingestion ADR-001](../ingestion/adr/001-segmented-wal-architecture.md#acknowledgement-and-termination).

---
title: "Junjo AI Studio Docker configuration reference"
description: "Configure supported services, persistent storage, networking, and authentication for a self-hosted Junjo AI Studio deployment."
---

Use this reference when configuring a Studio deployment. For the initial setup
and the first application/coding-agent connection, start with
[Deployment](/docs/studio/deployment/).

## Docker Images

Use the three image versions selected together by the supported distribution.
Keep the corresponding SDK and Studio telemetry contract compatible when
using native graph, Agent, and Store views. See the selected release's notes
before changing versions.

### Backend Service

**Image:** [mdrideout/junjo-ai-studio-backend](https://hub.docker.com/r/mdrideout/junjo-ai-studio-backend)

The backend serves the HTTP API used by the browser, coding-agent CLI, and
SDK. It manages authentication, canonical evaluation records, and evidence
queries:

- `junjo.db` holds accounts, credentials, datasets, cases, runs, and attempts.
- `metadata.db` is the telemetry file index, separate from canonical product data.
- DataFusion queries received spans in Parquet and the shared hot snapshot.
- Private RPCs coordinate recent evidence reads with ingestion.

### Ingestion Service

**Image:** [mdrideout/junjo-ai-studio-ingestion](https://hub.docker.com/r/mdrideout/junjo-ai-studio-ingestion)

Ingestion receives authenticated OTLP/gRPC **traces**. It writes segmented
Arrow IPC WAL data and flushes it to Parquet. It makes recent evidence
available to the backend through shared files and a private RPC service.

Ingestion authorization uses application telemetry API keys. Successful
validation can be reused for the configured short cache interval; invalid keys
and backend failures are not cached. The distribution's `.env.example` owns
the cache, buffering, backpressure, and flush settings.

### Frontend Service

**Image:** [mdrideout/junjo-ai-studio-frontend](https://hub.docker.com/r/mdrideout/junjo-ai-studio-frontend)

The frontend provides dataset/run comparisons, trace exploration, and native
Junjo execution and state views. The browser calls the backend API. The
prebuilt image serves the web UI on container port `26153`; `26151` is the
source repository's development server and is not the prebuilt image's port.

## Complete Docker Compose Configuration

### Minimal Build Configuration

The [minimal distribution's Compose file](https://github.com/mdrideout/junjo-ai-studio-minimal-build/blob/master/docker-compose.yml)
and [.env.example](https://github.com/mdrideout/junjo-ai-studio-minimal-build/blob/master/.env.example)
are the configuration source for the released stack. The
[canonical monorepo directory](https://github.com/mdrideout/junjo/tree/master/apps/studio/deployments/minimal)
owns changes to that distribution.

The Compose configuration supplies versioned images, prefixed service names,
a project-scoped network, persistent mounts, small-host settings, and
service-specific environment overrides. Preserve those relationships when
incorporating it into your own Compose project. This reference intentionally
links to the maintained file instead of carrying a separate Compose copy.

## Production Deployment

For a VM with HTTPS, use the
[VM/Caddy distribution](https://github.com/mdrideout/junjo-ai-studio-deployment-example).
It keeps the proxy routing and Studio configuration together. Its canonical
source is [apps/studio/deployments/vm-caddy](https://github.com/mdrideout/junjo/tree/master/apps/studio/deployments/vm-caddy).

<a id="production-deployment-1"></a>
### Reverse Proxy Setup

Expose the web UI, backend HTTP API, and OTLP/gRPC endpoint through their
configured public origins. The ingestion route requires a proxy that supports
gRPC; forwarding it as ordinary HTTP/1 traffic does not provide an OTLP/gRPC
connection. Keep the private service RPC ports inside the Studio network.

Use the distribution's Caddyfile and image together, including its required
DNS integration when using that setup. The frontend and backend must share a
registrable domain because Studio uses browser session cookies with
`SameSite=Strict`.

## Environment Variables Reference

The distribution's `.env.example` is the complete, release-specific list of
settings and defaults. The following groups explain the settings most often
needed during adoption.

### Common Configuration

| Setting | Purpose |
| --- | --- |
| `JUNJO_ENV` | Set `development` for the local endpoint configuration or `production` for configured public origins. The prebuilt frontend requires an explicit value. |
| `JUNJO_ALLOW_ORIGINS` | Allowed browser origins for backend CORS. Production can derive this from the configured frontend URL. Use exact origins when overriding. |

Do not add generic `PORT` or `GRPC_PORT` values to the shared `.env`. Backend
and ingestion have different listener roles; the Compose file pins each
service's internal configuration.

### Security (Backend and Ingestion)

| Setting | Purpose |
| --- | --- |
| `JUNJO_SESSION_SECRET` | Required session-signing secret. |
| `JUNJO_SECURE_COOKIE_KEY` | Required cookie-encryption key; must encode exactly 32 bytes in Base64. |
| `JUNJO_INTERNAL_GRPC_TOKEN` | Required backend/ingestion workload credential with at least 32 characters. |

The setup wizard generates these secrets. Manual setup instructions in the
distribution describe generating a separate value for each. Keep the internal
RPC token out of browser-facing and reverse-proxy containers; the canonical
frontend service explicitly clears it even when a shared `.env` is loaded.

Application telemetry and developer access credentials are issued in Studio:

| Credential | Consumer | Authorized destination |
| --- | --- | --- |
| `JUNJO_AI_STUDIO_API_KEY` | Application OTLP exporter | Ingestion, using `x-junjo-api-key` |
| `JUNJO_AI_STUDIO_CLI_TOKEN` | Coding-agent CLI or SDK | Backend evaluation/evidence API, using its granted scopes |

Neither credential substitutes for the other or for the internal RPC token.
The [connection guide](/docs/studio/deployment/#connect-your-application-and-coding-agent)
covers creation and verification.

### Database Storage

`JUNJO_HOST_DB_DATA_PATH` selects the host data directory mounted by backend
and ingestion. The minimal distribution defaults to `./.dbdata`. For a
persistent mounted volume, point it to the volume's existing mount directory.
Keep the matching container paths from the distribution.

### Logging

`JUNJO_LOG_LEVEL` selects the log verbosity. `JUNJO_LOG_FORMAT` selects the
backend's `json` or `text` output. Follow the distribution's current example
for defaults. Avoid copying secrets or customer payloads into support reports.

### Production URLs (Required for Production)

| Setting | Destination |
| --- | --- |
| `JUNJO_PROD_FRONTEND_URL` | Public Studio web UI origin, used for human evidence links. |
| `JUNJO_PROD_BACKEND_URL` | Public backend API origin, reachable by the browser and evaluation clients. |
| `JUNJO_PROD_INGESTION_URL` | Public OTLP/gRPC ingestion origin. |

The coding agent's `JUNJO_AI_STUDIO_BACKEND_BASE_URL` points to the backend
origin, not the UI or ingestion address. SDK/CLI control access requires HTTPS
outside loopback, including when using a VM or container hostname.

## Volume Mounts

Backend and ingestion must see the **same underlying files at their expected
container paths**. The backend reads Parquet and the hot snapshot directly;
a working network connection between the services does not replace the shared
storage requirement. The frontend is stateless.

### Local Directory Structure

| Data under the default `.dbdata` directory | Role |
| --- | --- |
| `sqlite/junjo.db` | Canonical accounts, credentials, datasets, cases, runs, and attempts |
| `sqlite/metadata.db` | Telemetry file index |
| `spans/wal/` | Recent trace storage in Arrow IPC segments |
| `spans/parquet/` | Flushed trace storage |
| `spans/hot_snapshot.parquet` | Shared snapshot used for recent-evidence queries |

Preserve the complete data directory across container replacement. Back up the
application database and telemetry consistently; retaining datasets alone
does not retain the execution evidence their links identify. Stop writers
before making a filesystem-copy backup and follow release-specific upgrade
instructions.

### Block Storage (Production)

Mount persistent block storage on the Studio host and configure
`JUNJO_HOST_DB_DATA_PATH`. Confirm the mount is present and writable before
starting the services. Use the VM distribution's instructions for a fresh
volume; an existing filesystem should be mounted, not formatted. Formatting
an existing device destroys its data.

## Port Mappings

### Internal Communication

The released minimal distribution uses these Compose service names and
container ports:

| Destination | Service and container port | Purpose |
| --- | --- | --- |
| Web UI | `junjo-ai-studio-frontend:26153` | Browser application |
| Backend API | `junjo-ai-studio-backend:26154` | Browser, SDK, and CLI HTTP API |
| Ingestion | `junjo-ai-studio-ingestion:26155` | Application OTLP/gRPC traces |
| Ingestion private RPC | `junjo-ai-studio-ingestion:50052` | Backend hot-snapshot coordination |
| Backend private RPC | `junjo-ai-studio-backend:50053` | Ingestion API-key validation |

Application exporters and evaluation clients do not use the two private RPC
ports. Preserve their private routing when adapting the deployment.

### External Access

For local host processes, the default frontend, backend, and ingestion
addresses use `localhost` and host ports `26153`, `26154`, and `26155`
respectively. `JUNJO_FRONTEND_HOST_PORT`, `JUNJO_BACKEND_HOST_PORT`, and
`JUNJO_INGESTION_HOST_PORT` can change those host ports without changing the
container ports.

For remote access, use the HTTPS origins configured by your reverse proxy.
The backend must be reachable from the coding agent's execution environment
as well as from the human's browser. A localhost-only backend does not enable
remote evaluation access just because the web UI is reachable.

## Resource Requirements

The supported small-host profile is designed for a 1GB RAM VM with a shared
vCPU. The application, model clients, and evaluation execution can run on
other machines. Deployment settings include backend memory and query limits,
with swap guidance in the distribution.

Actual capacity depends on span volume, payload size, retained history, and
concurrent queries. Measure those workloads when allocating CPU, memory, and
disk; this host profile is not a claim of a fixed throughput or retention limit.

## Network Configuration

### Docker Network

Compose creates a project-scoped `junjo-network`; the actual Docker network
name includes the Compose project name. There is no globally fixed
`junjo_network` name to pre-create.

An application in the same Compose project can join that network and use the
ingestion service name. For a separate Compose project, either deliberately
attach to the actual existing Studio network or use the configured externally
reachable endpoint. Do not assume an unconnected container can resolve Studio
service names, and do not use its own `localhost` as the Studio destination.

## Scaling Considerations

### Vertical Scaling

Keep backend and ingestion together on the supported shared-storage host.
Increase CPU, memory, and disk performance as measured workloads require;
review the distribution's memory/query profile alongside host capacity.

Independent application experiments can record their runs into the same
Studio instance. This does not turn Studio into a distributed application
executor. Splitting the storage-reading backend and ingestion across unrelated
VMs, or duplicating them behind a load balancer, is not the supported Compose
topology.

## Troubleshooting

### Service Won't Start

Run `docker compose ps` and inspect logs from the distribution directory.
The canonical service names are `junjo-ai-studio-backend`,
`junjo-ai-studio-ingestion`, and `junjo-ai-studio-frontend`; for example,
`docker compose logs junjo-ai-studio-ingestion` reads ingestion logs.

Check required secrets, host port conflicts, the persistent mount, and write
permissions. Let Compose create its project network. Preserve persistent data
while investigating; deleting volumes or formatting disks is not a general
startup fix.

### API Errors

Verify the actual backend origin, allowed browser origin, and production URL
configuration. Check backend logs. If the browser works but the CLI fails,
check the developer access token's scopes and expiration, and confirm HTTPS
for a non-loopback origin. An ingestion API key cannot authenticate the CLI.

## Next Steps

- [Connect your application and coding agent](/docs/studio/deployment/#connect-your-application-and-coding-agent).
- [Investigate datasets, runs, and execution evidence](/docs/studio/overview/).
- [Run a recursive self improvement cycle](/docs/recursive-self-improvement/).

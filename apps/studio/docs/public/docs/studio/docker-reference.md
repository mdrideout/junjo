---
title: "Docker Reference"
---
<!-- migrated-from: sdks/python/docs/docker_reference.rst; source-hash: sha256:f47f389bb891dea24407ef87ba571bf1a7a28f9da1b221da75590a6179dd651c -->

Junjo AI Studio is distributed as three Docker images that work together to provide a complete observability platform for AI workflows. This page provides detailed reference information for deploying and configuring these services.

**Quick Start:** For a ready-to-use setup, see the [Junjo AI Studio Minimal Build Template](https://github.com/mdrideout/junjo-ai-studio-minimal-build). For a complete production example with reverse proxy and HTTPS, see the [Junjo AI Studio Deployment Example](https://github.com/mdrideout/junjo-ai-studio-deployment-example). More details in [Deployment](/docs/studio/deployment/).

## Docker Images

### Backend Service

**Image:** [mdrideout/junjo-ai-studio-backend](https://hub.docker.com/r/mdrideout/junjo-ai-studio-backend)

The backend service provides the HTTP API, authentication, and query capabilities.

**Storage and query model (current):**

- **SQLite** for users / sessions / API keys
- **SQLite metadata index** for fast lookup of which Parquet files may contain a trace/service
- **Parquet** files for span storage (cold tier)
- **DataFusion** to query Parquet (cold + hot snapshot) and deduplicate results

**Notes:**

- Indexes new Parquet files asynchronously (polls the shared Parquet directory)
- Calls ingestion internal gRPC (`:50052`) per query to generate a hot snapshot and return a bounded list of recently-flushed cold Parquet paths (bridges flush→index lag)

### Ingestion Service

**Image:** [mdrideout/junjo-ai-studio-ingestion](https://hub.docker.com/r/mdrideout/junjo-ai-studio-ingestion)

The ingestion service provides high-throughput OpenTelemetry trace reception using a segmented Arrow IPC write-ahead log (WAL) that flushes to date-partitioned Parquet files (constant memory flush).

**Ports:**

- `26155` - OpenTelemetry gRPC ingestion endpoint exposed by the ingestion service
- `50052` - Internal gRPC for backend queries (PrepareHotSnapshot / FlushWAL) (internal)

**Notes:**

- This is the primary endpoint where your Junjo workflows send trace telemetry
- Uses segmented Arrow IPC WAL for durability and throughput
- Flushes WAL → Parquet and maintains a bounded list of recently flushed Parquet paths for query bridging
- Reuses successful API-key validation for a short fixed interval (10 seconds
  by default), with same-key refresh coalescing over one multiplexed backend
  auth gRPC channel (`:50053`)
- Never caches invalid keys or backend failures and never serves an expired
  authorization stale; cold-path saturation is retryable

### Frontend Service

**Image:** [mdrideout/junjo-ai-studio-frontend](https://hub.docker.com/r/mdrideout/junjo-ai-studio-frontend)

The frontend service provides the interactive web UI for visualizing and debugging AI workflows.

**Ports:**

- `26153` - Production-build web UI HTTP server (the port served by the prebuilt image)
- `26151` - Development web UI HTTP server (available only in the junjo-ai-studio source repository's development stack)

**Notes:**

- Static web application that communicates with the backend API
- Requires backend service to be running and healthy
- Serves interactive graph visualizations and state debugging tools

## Complete Docker Compose Configuration

### Minimal Build Configuration

This is the standard configuration for running Junjo AI Studio, suitable for both local development and as a starting point for production.

```yaml title="docker-compose.yml"
# Junjo AI Studio - Minimal Build
# A lightweight, self-hostable AI workflow debugging platform.
# https://github.com/mdrideout/junjo-ai-studio-minimal-build

services:
  backend:
    image: mdrideout/junjo-ai-studio-backend:latest
    restart: unless-stopped
    volumes:
      # Database storage (required for all modes)
      - ${JUNJO_HOST_DB_DATA_PATH:-./.dbdata}:/app/.dbdata
    ports:
      - "26154:26154" # Local backend API
    networks:
      - junjo-network
    env_file:
      - .env
    environment:
      # Private backend-to-ingestion RPC; not an OTLP endpoint
      - INGESTION_HOST=ingestion
      - INGESTION_PORT=50052
      # Pinned so a stray GRPC_PORT in the shared .env cannot rewire the auth RPC listener
      - GRPC_PORT=50053
      # Enable migrations on startup
      - RUN_MIGRATIONS=true
      # Database paths (hardcoded for Docker, users configure host mount via JUNJO_HOST_DB_DATA_PATH)
      - JUNJO_SQLITE_PATH=/app/.dbdata/sqlite/junjo.db
      - JUNJO_METADATA_DB_PATH=/app/.dbdata/sqlite/metadata.db
      - JUNJO_PARQUET_STORAGE_PATH=/app/.dbdata/spans/parquet

  ingestion:
    image: mdrideout/junjo-ai-studio-ingestion:latest
    restart: unless-stopped
    volumes:
      # Database storage (required for all modes)
      - ${JUNJO_HOST_DB_DATA_PATH:-./.dbdata}:/app/.dbdata
    ports:
      - "26155:26155" # Local OTLP endpoint (authenticated via API key)
    networks:
      - junjo-network
    env_file:
      - .env
    environment:
      # Private ingestion-to-backend auth RPC
      - BACKEND_GRPC_HOST=backend
      - BACKEND_GRPC_PORT=50053
      # Pinned so stray GRPC_PORT / INTERNAL_GRPC_PORT values in the shared .env cannot rewire these listeners
      - GRPC_PORT=26155
      - INTERNAL_GRPC_PORT=50052
      # Arrow IPC WAL directory
      - WAL_DIR=/app/.dbdata/spans/wal
      # Hot snapshot path (backend reads this file directly)
      - SNAPSHOT_PATH=/app/.dbdata/spans/hot_snapshot.parquet
      # Parquet output directory (backend indexer watches this)
      - PARQUET_OUTPUT_DIR=/app/.dbdata/spans/parquet
    depends_on:
      backend:
        condition: service_started
    healthcheck:
      test: ["CMD", "/bin/grpc_health_probe", "-addr=localhost:50052"]
      interval: 5s
      timeout: 3s
      retries: 5
      start_period: 5s

  frontend:
    image: mdrideout/junjo-ai-studio-frontend:latest
    restart: unless-stopped
    ports:
      - "26153:26153" # Production-build web UI
    env_file:
      - .env
    networks:
      - junjo-network
    depends_on:
      backend:
        condition: service_started

networks:
  junjo-network:
    name: junjo_network
    driver: bridge
```

## Production Deployment

For a complete production setup on a Virtual Machine (VM) including:

- **Caddy Reverse Proxy** for automatic HTTPS
- **Subdomain routing** (e.g., `junjo.example.com`)
- **Block storage** configuration

Please refer to the [Junjo AI Studio Deployment Example](https://github.com/mdrideout/junjo-ai-studio-deployment-example) repository.

## Environment Variables Reference

This section details the environment variables used to configure Junjo AI Studio. These are typically defined in a `.env` file.

### Common Configuration

`JUNJO_ENV`

: **Optional** for the backend (defaults to `development`), but the prebuilt frontend container requires it to be set explicitly. Environment mode.

  - `development` (default): Uses localhost and standard ports.
  - `production`: Expects production hostname and subdomains.

`JUNJO_ALLOW_ORIGINS`

: **Optional.** Comma-separated list of allowed CORS origins for API requests.

  - **Development Default:** `http://localhost:26151,http://localhost:26153`
  - **Production:** Auto-derived from `JUNJO_PROD_FRONTEND_URL` if not set.

### Security (Backend and Ingestion)

These keys secure session cookies and must be Base64-encoded strings.

`JUNJO_SESSION_SECRET`

: **Required.** Signing key for session integrity (prevents tampering).

  - **Generate:** `openssl rand -base64 32`

`JUNJO_SECURE_COOKIE_KEY`

: **Required.** Encryption key for session confidentiality (prevents reading).

  - **Generate:** `openssl rand -base64 32`

`JUNJO_INTERNAL_GRPC_TOKEN`

: **Required.** Shared workload credential authenticating internal backend and
  ingestion gRPC calls. It must contain at least 32 characters and must not be
  exposed to browser-facing or reverse-proxy containers.

  - **Generate:** `openssl rand -base64 32`

### Database Storage

`JUNJO_HOST_DB_DATA_PATH`

: **Optional.** Path on the host machine where database files are stored. Consumed by Docker Compose interpolation, which defaults it to `./.dbdata`.

  - **Development Default:** `./.dbdata` (local directory)
  - **Production:** Use a mounted block storage path (e.g., `/mnt/junjo-data`).

### Logging

`JUNJO_LOG_LEVEL`

: Minimum severity level for logs.

  - Values: `debug`, `info` (default), `warn`, `error`.

`JUNJO_LOG_FORMAT`

: Output format for logs.

  - `json` (default): Machine-readable, recommended for production.
  - `text`: Human-readable, colored output for development.

### Production URLs (Required for Production)

When `JUNJO_ENV=production`, these variables configure public access points.

`JUNJO_PROD_FRONTEND_URL`

: The public URL where users access the web UI (e.g., `https://app.example.com`).

`JUNJO_PROD_BACKEND_URL`

: The public URL for the backend API (e.g., `https://api.example.com`). Must share the same root domain as the frontend.

`JUNJO_PROD_INGESTION_URL`

: The public URL for the ingestion service (e.g., `https://ingestion.example.com`).

### AI Service Keys (Optional)

API keys for LLM features in the prompt playground.

- `GEMINI_API_KEY`
- `OPENAI_API_KEY`
- `ANTHROPIC_API_KEY`

## Volume Mounts

The backend and ingestion services require persistent storage for their databases; the frontend is stateless. The recommended approach is to use either local directories or block storage volumes.

### Local Directory Structure

```text
.
├── docker-compose.yml
├── .env
└── .dbdata/
    ├── sqlite/                # Backend SQLite (junjo.db + metadata.db)
    └── spans/
        ├── wal/               # Arrow IPC WAL segments (hot)
        ├── parquet/           # Date-partitioned Parquet files (cold)
        └── hot_snapshot.parquet
```

**Create directories:**

```bash
mkdir -p .dbdata/sqlite .dbdata/spans/wal .dbdata/spans/parquet
chmod -R 755 .dbdata
```

### Block Storage (Production)

For production deployments, mount block storage at a consistent location:

```bash
# Example: Mount block storage
sudo mkfs.ext4 /dev/disk/by-id/scsi-0DO_Volume_junjo-data
sudo mkdir -p /mnt/junjo-data
sudo mount -o defaults,nofail /dev/disk/by-id/scsi-0DO_Volume_junjo-data /mnt/junjo-data

# Create database directories
sudo mkdir -p /mnt/junjo-data/sqlite /mnt/junjo-data/spans/wal /mnt/junjo-data/spans/parquet
sudo chown -R $USER:$USER /mnt/junjo-data
```

Update volume paths in docker-compose.yml:

```yaml
volumes:
  - /mnt/junjo-data:/app/.dbdata
```

## Port Mappings

### Internal Communication

Junjo AI Studio services communicate privately inside the Docker network for
hot-snapshot and API-key validation RPCs. Junjo library applications do not use
these private RPC ports as telemetry endpoints:

```text
Frontend -> Backend (26154)
Backend -> Ingestion (50052, internal hot-snapshot / WAL-flush RPC)
Ingestion -> Backend (50053, internal API-key validation RPC)
Same-network application -> Ingestion (26155, OTLP gRPC)
```

### External Access

These ports need to be accessible:

**Development:**

- Frontend: `http://localhost:26153` (production-build web UI served by the prebuilt image; `http://localhost:26151` applies only to the junjo-ai-studio source repository's development stack)
- Backend API: `localhost:26154` (Optional, usually only accessed by frontend)
- Ingestion: `localhost:26155` (Applications running on the local machine connect here)
- Same-network container ingestion: `ingestion:26155`

If your Junjo application runs in Docker, it only needs to be on the same Docker
network as the Junjo AI Studio ingestion service. Use `host="ingestion"` and
`port="26155"` when the ingestion service container is named `ingestion`.
Use `localhost:26155` only when the application runs directly on the local
machine.

**Production (with reverse proxy):**

- Frontend: `https://junjo.example.com` (Web UI)
- Backend API: `https://api.junjo.example.com` (API)
- Ingestion: `https://ingestion.example.com` (gRPC with TLS - see Caddyfile routing example)

See [Deployment](/docs/studio/deployment/) for production deployment examples with Caddy reverse proxy.

## Resource Requirements

Junjo AI Studio is designed to run on minimal resources:

**Minimum Recommended Resources:**

- **CPU:** 1 shared vCPU
- **RAM:** 1 GB
- **Storage:** 10 GB (more for long-term trace retention)

## Network Configuration

### Docker Network

All services should run on the same Docker network for internal communication:

```yaml
networks:
  junjo-network:
    name: junjo_network
    driver: bridge
```

Applications in separate Docker Compose projects can join the same network:

```yaml
services:
  app:
    build: .
    networks:
      - junjo-network

networks:
  junjo-network:
    external: true
    name: junjo_network
```

## Production Deployment

### Reverse Proxy Setup

For production, use a reverse proxy like Caddy or Nginx to provide:

- Automatic HTTPS with Let's Encrypt
- Subdomain routing
- Load balancing (if scaling horizontally)

Example Caddyfile:

```text title="Caddyfile"
# Junjo AI Studio routing block
junjo.example.com, *.junjo.example.com {
  tls your.email@gmail.com {
    dns cloudflare {env.CLOUDFLARE_API_TOKEN} # Created inside CloudFlare and set in the .env file
    resolvers 1.1.1.1 # Cloudflare DNS is recommended for this plugin
  }

  # backend: api.junjo.example.com
  @api host api.junjo.example.com
  handle @api {
    reverse_proxy backend:26154
  }

  # ingestion: ingestion.junjo.example.com
  @ingestion host ingestion.junjo.example.com
  handle @ingestion {
    reverse_proxy h2c://ingestion:26155
  }

  # frontend: Fallback for the root domain
  handle {
    reverse_proxy frontend:26153
  }
}
```

The `dns cloudflare` directive requires a Caddy build that includes the Cloudflare DNS module (as used in the deployment-example repository); with stock Caddy and a public DNS A record, the `tls`/`dns` block can be omitted for standard certificate issuance.

See the [Junjo AI Studio Deployment Example](https://github.com/mdrideout/junjo-ai-studio-deployment-example) for a complete production setup.

## Scaling Considerations

### Vertical Scaling

For most deployments, vertical scaling is sufficient:

- Increase CPU/RAM allocation
- Use faster disk (NVMe SSDs)
- Increase Docker memory limits
- Split frontend, backend, and ingestion services to separate virtual machines, scaling each's resources as necessary.

## Troubleshooting

### Service Won't Start

Check logs for specific errors:

```bash
docker compose logs backend
docker compose logs ingestion
docker compose logs frontend
```

Common issues:

- Missing environment variables in `.env`
- Port conflicts (check with `netstat -tlnp`)
- Permission issues with volume mounts
- `junjo_network` was pre-created manually — do not run `docker network create`; start the AI Studio stack first so Docker Compose creates and labels the network, then application compose projects that declare it `external` can attach

### API Errors

If the web UI shows API errors:

- Check CORS settings in backend (`JUNJO_ALLOW_ORIGINS`)
- Verify frontend can reach backend API
- Check backend logs for specific errors
- Verify session secret is set in production

## Next Steps

- See [Junjo Ai Studio](/docs/studio/overview/) for setup and configuration
- Review [Deployment](/docs/studio/deployment/) for production deployment examples
- Explore [Opentelemetry](/docs/observability/opentelemetry/) for application instrumentation

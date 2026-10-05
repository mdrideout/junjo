# Junjo AI Studio

> Junjo (順序) - order, sequence, procedure

**Junjo AI Studio** is an open source, self-hostable AI Agent and Workflow debugging and eval platform for any OpenTelemetry instrumented AI application. 

The [Junjo Python Library](https://github.com/mdrideout/junjo/tree/master/sdks/python) is a framework for structuring AI logic and enhancing Otel span data to improve observability and developer velocity. Junjo remains decoupled from your LLM implementations and business logic, providing a layer of organization, execution, and telemetry to your existing application.

Gain complete visibility to the state of the application, and every change LLMs make to the application state. Complex, mission critical AI workflows are made transparent and understandable with Junjo.

<img src="https://junjo.ai/docs-assets/generated/python/junjo-screenshot.png" width="800" />

_Junjo AI Studio Workflow Debugging Screenshot_

### Key Features

- 🔍 **Real-time LLM Decision Visibility** - See every decision your LLM makes and the data it uses
- 🧭 **Agent Execution Diagnostics** - Inspect ordered model and Tool operations without fabricating a Graph
- 🔀 **Transparent Concurrency** - Debug state changes from concurrently executed AI workflow steps
- 📊 **OpenTelemetry Native** - Standards-based telemetry ingestion via gRPC
- 🎯 **Workflow Debugging Interface** - Visual step-by-step debugging of AI graph workflows
- 🧾 **Evidence Integrity** - Verify Store reconstruction, payload availability, loss signals, and nested execution parentage
- 🔒 **Production-Ready Security** - Authentication, user accounts, and server-side sessions
- 🚀 **Low Resource, High-Performance Ingestion** - Designed for high-throughput in low resource environments
- 💾 **Shared vCPU, 1GB RAM** - Production grade telemetry on a $5 / month virtual machine

---

## Table of Contents

- [Quick Start](#quick-start)
- [Source Development](#source-development)
- [Features](#features)
- [Architecture](#architecture)
- [Prerequisites](#prerequisites)
- [Configuration](#configuration)
- [Production Deployment](#production-deployment)
- [Advanced Topics](#advanced-topics)
- [Testing](#testing)
- [Troubleshooting](#troubleshooting)
- [Resources](#resources)

---

## Quick Start

Canonical deployment source lives under [`deployments/`](deployments/) in this
monorepo. Standalone deployment repositories are designated one-way release
mirrors so operators can clone a small focused repository. Deployment changes
must be contributed to the canonical directories here; direct mirror changes
are overwritten by the release publication workflow.

If you want to use Junjo AI Studio rather than modify its source code, start
with the generated **[Junjo AI Studio Minimal Build](https://github.com/mdrideout/junjo-ai-studio-minimal-build)**
distribution mirror.

### Steps

1. **Clone the minimal build repository**
   ```bash
   git clone https://github.com/mdrideout/junjo-ai-studio-minimal-build.git
   cd junjo-ai-studio-minimal-build
   ```

2. **Choose setup mode**

   Recommended:
   ```bash
   ./scripts/junjo setup
   ```

   Manual:
   ```bash
   cp .env.example .env
   ```

   Then generate and set the internal gRPC token:
   ```bash
   openssl rand -base64 32
   ```

   Open `.env` and replace the placeholder value:
   - Replace `your_internal_grpc_token_here` in `JUNJO_INTERNAL_GRPC_TOKEN` with the generated value

   For production deployments, also configure:
   ```bash
   JUNJO_ENV=production
   JUNJO_PROD_INGESTION_URL=https://ingestion.example.com
   ```

3. **Start all services**
   ```bash
   docker compose up
   ```

4. **Access Junjo AI Studio**
   - Follow the exact URL and port guidance in the [minimal build README](https://github.com/mdrideout/junjo-ai-studio-minimal-build/blob/master/README.md).

5. **Create your first user**
   - Navigate to your Studio URL
   - Follow the setup wizard to create your admin account

6. **Create an API key** (for sending telemetry from your Junjo app)
   - Sign in to the web UI
   - Open the **API Keys** page from the sidebar
   - Click **Create API Key**
   - Copy the 64-character key from the API Keys page (use the copy button)
   - Use this key in your Junjo Python Library application

### Useful Docker Compose Commands

```bash
# View logs from all services
docker compose logs -f

# View logs from specific service
docker compose logs -f junjo-ai-studio-app
docker compose logs -f junjo-ai-studio-ingestion

# Stop services (keeps data)
docker compose down

# Restart a specific service
docker compose restart junjo-ai-studio-app

# View running containers and their status
docker compose ps
```

A fresh start means resetting the host data directory, which `docker compose down -v` does not remove. Follow the [reset procedure](deployments/RESET.md).

### Next Steps

Configure your [Junjo Python Library](https://github.com/mdrideout/junjo/tree/master/sdks/python) application using the setup and endpoint guidance from the minimal build repository.

**Version compatibility:** Junjo AI Studio and the Junjo Python Library must run
releases that share the same telemetry contract. A mismatched SDK may still send
raw spans, but Studio does not apply a fallback semantic parser: Workflow graphs,
Agent diagnostics, and verified Store reconstruction require the active
contract. Upgrade the paired releases together.

This repository contains the complete open source Junjo AI Studio codebase. If you want to run or modify the source code in this repository, see [Source Development](#source-development) below.

For operator-managed deployment behind your own reverse proxy, use the
[minimal distribution](deployments/minimal) or the
[VM/Caddy distribution](deployments/vm-caddy), and set
`JUNJO_PROD_INGESTION_URL` to your public ingestion URL. Their standalone
repositories are generated release mirrors of these canonical directories.

---

## Source Development

This directory contains the complete open source Junjo AI Studio codebase. From
the Junjo platform repository root, enter the Studio project before running its
commands:

```bash
cd apps/studio
```

Use the default hot-reload local stack when you want to develop or modify Junjo AI Studio itself:

```bash
./scripts/junjo setup
docker compose up --build
```

Local URLs use the same port numbers inside Docker and on localhost:
- `JUNJO_BUILD_TARGET=development` with `COMPOSE_PROFILES=development`: Studio UI `http://localhost:26151` (the Vite development server, which proxies API requests to the backend), backend API `http://localhost:26154`, OTLP `grpc://localhost:26155`
- `JUNJO_BUILD_TARGET=production` with `COMPOSE_PROFILES` empty: Studio UI and API `http://localhost:26154`, OTLP `grpc://localhost:26155`

The two settings go together, and the setup wizard writes both. The Vite development server runs only in the `development` Compose profile; a production build serves the UI from the backend.

A development build compiles the backend inside its container, which needs several GB of memory. The setup wizard therefore leaves the backend's container limits off for a development build and applies the selected memory profile to a production build. An `.env` written before the Rust backend has the limits set: rerun `./scripts/junjo setup`, or set the four `JUNJO_BACKEND_*` limits as `.env.example` shows.

The port numbers stay the same for same-network containers. Only the hostname changes: use `backend:26154` for the backend API and `ingestion:26155` for OTLP from another container on this Compose network.

After changing `JUNJO_BUILD_TARGET`, rerun `docker compose up --build` so Docker rebuilds the matching image targets. Use `-d` only when you intentionally want detached containers.

For service-specific development notes, see [backend/README.md](./backend/README.md), [frontend/README.md](./frontend/README.md), and [ingestion/README.md](./ingestion/README.md).

---

## Features

### What Can You Do With Junjo AI Studio?

**Observability & Debugging:**
- View complete Workflow and Agent execution traces
- Explore declared Workflow Graph paths and realized Agent operation timelines
- Inspect normalized model requests/responses and Tool arguments/results
- Navigate backend-verified Workflow and Agent Store transitions
- Diagnose partial evidence, payload policy, and OTLP loss signals
- Follow semantic parents and causally nested Workflows or Agents
- Monitor performance and latency

**OpenTelemetry Integration:**
- Standards-compliant OTLP/gRPC ingestion endpoint
- Automatic trace collection from Junjo Python Library
- Custom span attributes for AI-specific metadata

**Multi-Service Architecture:**
- Decoupled ingestion for high throughput
- Web UI for visualization
- REST API for programmatic access

---

## Architecture

The Junjo AI Studio runs as two services, and its web UI is a React application that the backend serves:

### 1. Backend (`backend`)
- **Tech Stack**: Rust (axum, tonic), SQLite, DataFusion
- **Responsibilities**:
  - HTTP REST API
  - Serving the web UI on the same origin as the API
  - User authentication & session management
  - Span querying & analytics
  - Semantic Workflow and Agent diagnostics
  - Shared Store reconstruction and evidence-integrity verification

### 2. Ingestion Service (`ingestion`)
- **Tech Stack**: Rust, gRPC (tonic), Arrow IPC, Parquet
- **Responsibilities**:
  - OpenTelemetry OTLP/gRPC endpoint
  - High-throughput span ingestion with backpressure
  - Write-Ahead Log using Arrow IPC segments
  - Flush WAL to date-partitioned Parquet files (cold storage)
  - Prepare hot snapshots for real-time queries

### 3. Frontend (`frontend`)
- **Tech Stack**: React, TypeScript
- **Delivery**: built into the application image and served by the backend; in development the Vite server serves it
- **Responsibilities**:
  - Web UI for Workflow Graph visualization
  - Dynamic Agent operation timelines and evidence inspection
  - Verified Store state navigation and nested executable links
  - User management

**Data Flow (Two-Tier Architecture):**
```
Junjo Python App → Ingestion Service (gRPC) → Arrow IPC WAL
                                                    ↓
                                         ┌─────────┴─────────┐
                                         ↓                   ↓
                                    FlushWAL RPC    PrepareHotSnapshot RPC
                                         ↓                   ↓
                                  Parquet files         Hot snapshot
                                  (COLD tier)          (HOT tier)
                                         ↓                   ↓
                                         └─────────┬─────────┘
                                                   ↓
                                    Backend Service (DataFusion)
                                         ↓
                                  Merged query results
                                         ↓
                                     Frontend UI
```

**How it works:**
- **Ingestion** receives OTLP spans and writes them to Arrow IPC WAL segments
- **FlushWAL** (periodic/manual) converts WAL segments to date-partitioned Parquet files (COLD tier)
- **PrepareHotSnapshot** creates an on-demand Parquet file from unflushed WAL data (HOT tier) and returns a bounded list of recently flushed cold Parquet files (`recent_cold_paths`) to bridge indexing lag
- **Backend** uses DataFusion to query COLD (SQLite-indexed + `recent_cold_paths`) and HOT Parquet files, merging results with deduplication by `(trace_id, span_id)` (COLD wins)

---

## Prerequisites 

### Required
- **Docker** and **Docker Compose** (for contributor development and local smoke tests)

### Optional (Development)
- **Rust toolchain** via rustup and **protoc 30.2** (for backend and ingestion development; see [PROTO_VERSIONS.md](PROTO_VERSIONS.md))
- **Python 3** (for the setup wizard and repository tooling scripts)
- **Node.js 18+** (for frontend development)

### For Production Deployment
- A domain or subdomain for hosting (see [Deployment Requirements](#deployment-requirements))
- TLS termination in your chosen reverse proxy or ingress layer

---

## Configuration

### Environment Variables

Junjo AI Studio uses a single `.env` file at the root of the project. All services read from this file.

For a guided setup wizard that writes critical `.env` values (including memory tuning profiles), run:

```bash
./scripts/junjo setup
```

#### Key Configuration Variables

```bash
# === Build & Environment ===========================================
# Build Target: development | production
JUNJO_BUILD_TARGET="development"

# Compose profile: "development" starts the Vite development server.
# Leave empty for a production build, where the backend serves the UI.
COMPOSE_PROFILES="development"

# Running Environment: development | production
# (production turns on Secure session cookies and requires
# JUNJO_PROD_INGESTION_URL)
JUNJO_ENV="development"

# === Security (REQUIRED) ===========================================
# Shared by the backend and ingestion. At least 32 characters.
# Generate with: openssl rand -base64 32
JUNJO_INTERNAL_GRPC_TOKEN=your_internal_grpc_token_here

# === Production (REQUIRED when JUNJO_ENV=production) ===============
# Public ingestion URL. The UI shows it in SDK setup instructions.
# JUNJO_PROD_INGESTION_URL=https://ingestion.example.com

# === Database Storage ==============================================
# Where database files are stored on your host machine/VM
JUNJO_HOST_DB_DATA_PATH=./.dbdata

# === Logging =======================================================
JUNJO_LOG_LEVEL=info        # debug | info | warn | error
JUNJO_LOG_FORMAT=json       # json | text
```

**See `.env.example` for complete configuration with detailed comments.**

### Database Storage Configuration

Junjo AI Studio stores all database files in a single location that you configure. Simply set where you want the data stored on your host machine, and Docker handles the rest.

#### Development Setup

For local development, use a relative path:

```bash
# .env file
JUNJO_HOST_DB_DATA_PATH=./.dbdata
JUNJO_BUILD_TARGET=development
COMPOSE_PROFILES=development
```

This stores databases in `./.dbdata` directory next to your `compose.yaml`.
Docker can create the directory automatically for an ordinary first start. For
a greenfield reset, follow `TESTING.md` and create the empty shared root before
starting Compose so backend and ingestion do not race to create it.

**Benefits:**
- Easy to reset by deleting the directory
- No special setup required
- Works out of the box

#### Production Setup with Block Storage

For production deployments with persistent storage (DigitalOcean Volumes, AWS EBS, Google Persistent Disk):

**1. Mount your block storage:**
```bash
# DigitalOcean Droplet example
sudo mount /dev/disk/by-id/scsi-0DO_Volume_junjo /mnt/junjo-data

# AWS EC2 example
sudo mount /dev/xvdf /mnt/junjo-data

# Google Cloud example
sudo mount /dev/disk/by-id/google-junjo-data /mnt/junjo-data
```

**2. Update your `.env` file:**
```bash
JUNJO_HOST_DB_DATA_PATH=/mnt/junjo-data
JUNJO_BUILD_TARGET=production
COMPOSE_PROFILES=
```

**3. Start services:**
```bash
docker compose up --build
```

**Benefits:**
- Data persists across container restarts
- Data survives even if you delete and recreate containers
- Easy to backup by snapshotting the volume
- Can detach and reattach to different instances

#### Important Notes

- The `JUNJO_HOST_DB_DATA_PATH` variable is the ONLY path you need to configure
- Container-internal paths are set automatically in `compose.yaml`
- If `JUNJO_HOST_DB_DATA_PATH` is not set, it defaults to `./.dbdata`
- The backend and ingestion services share the same storage location

#### Database & Storage Types

Junjo AI Studio uses embedded databases and file-based storage:

| Storage | Purpose | Type |
|---------|---------|------|
| **SQLite** | User data, API keys, sessions | Single file |
| **Parquet** | Span analytics (COLD tier) | Date-partitioned files |
| **Arrow IPC WAL** | Ingestion buffer (HOT tier) | Directory of IPC segments |
| **Hot Snapshot** | Real-time query cache | Single Parquet file |

All are stored under `JUNJO_HOST_DB_DATA_PATH` on your host machine. The backend uses **DataFusion** to query Parquet files directly.

### Creating API Keys

After starting Junjo AI Studio:
1. Sign in to the web UI exposed by your active build target (`http://localhost:26151` for development, `http://localhost:26154` for production)
2. Open the **API Keys** page from the sidebar
3. Click **Create API Key**
4. Copy the 64-character key from the API Keys page (use the copy button)
5. Use this key in your Junjo Python Library application

---

## Production Deployment

The Studio runtime root defines the production runtime contract:
- three required settings: `JUNJO_ENV=production`, `JUNJO_INTERNAL_GRPC_TOKEN`, and the public ingestion URL in `JUNJO_PROD_INGESTION_URL`
- one origin for the Studio UI and its API, served by the backend on port 26154

Supported deployment topology source is owned separately under
[`deployments/`](deployments/). Bring your own reverse proxy, ingress, or load
balancer around the [minimal distribution](deployments/minimal), or use the
[VM/Caddy distribution](deployments/vm-caddy) as a complete example.

If you route directly to this source repository's Compose services, target `backend:26154` for Studio and `ingestion:26155` for OTLP.

### Deployment Requirements

Production needs two hostnames:
- one for Studio, routed to the backend on port 26154, which serves the UI and the API on one origin
- one for ingestion, routed to port 26155 (OTLP/gRPC)

There is no separate API hostname and no shared-domain requirement.

In production the session cookie is `Secure`, so serve the Studio hostname over HTTPS.

### Supported Deployment Distributions

The paths below are canonical. The linked standalone repositories are the
generated release distributions for operator use, not contribution targets.

#### Junjo AI Studio Minimal Build

- **Canonical source:** [`deployments/minimal`](deployments/minimal)
- **Designated release mirror:** [mdrideout/junjo-ai-studio-minimal-build](https://github.com/mdrideout/junjo-ai-studio-minimal-build)

A minimal, standalone repository with just the core Junjo AI Studio components using pre-built Docker images.

**Best for:**
- Quick testing of Junjo AI Studio
- Simple production deployments with explicit public URLs
- Integration into existing infrastructure

#### Junjo AI Studio Deployment Example

- **Canonical source:** [`deployments/vm-caddy`](deployments/vm-caddy)
- **Designated release mirror:** [mdrideout/junjo-ai-studio-deployment-example](https://github.com/mdrideout/junjo-ai-studio-deployment-example)

A complete, production-ready example that includes a Junjo Python Library application alongside the server infrastructure.

**Best for:**
- End-to-end deployment examples
- Learning how to configure your Junjo app with the server
- VM deployment guide (Digital Ocean Droplet, AWS EC2, etc.)
- One complete reverse-proxy/TLS example

The canonical [VM/Caddy README](deployments/vm-caddy/README.md) provides
step-by-step deployment instructions.

### Docker Compose - Production Images

Junjo AI Studio is built and deployed to **Docker Hub** with each GitHub release:

- **Studio application** (backend API and web UI): [mdrideout/junjo-ai-studio-app](https://hub.docker.com/r/mdrideout/junjo-ai-studio-app)
- **Ingestion Service**: [mdrideout/junjo-ai-studio-ingestion](https://hub.docker.com/r/mdrideout/junjo-ai-studio-ingestion)

**Example Compose file:** [`deployments/minimal/docker-compose.yml`](deployments/minimal/docker-compose.yml)

Use these images in the deployment stack you own. For complete working examples, start from the minimal-build or deployment-example repositories.

### VM Resource Requirements

Junjo AI Studio is designed to be low resource:
- **Minimum**: Shared vCPU + 1GB RAM
- **Databases**: SQLite (embedded, low overhead)
- **Recommended**: 1 vCPU + 2GB RAM for production workloads

---

## Advanced Topics

### Stable execution links

Applications should persist Junjo Workflow or Agent runtime IDs, not
OpenTelemetry trace/span IDs. A signed-in Studio user can follow a stable
frontend link of this form:

```text
/resolve/executable?service_namespace=junjo.examples&service_name=ai-chat&executable_type=agent&runtime_id=<run-id>&destination=detail
```

The authenticated frontend renders the semantic execution page immediately.
While telemetry is still arriving, it shows an in-context pending message and
continues exact resolution with capped backoff. When the execution becomes
available, Studio replaces the semantic URL with the ordinary Agent, Workflow,
or full-trace detail URL. One-Node Workflows open with that exact Node selected.
Resolution requires service namespace, service name, executable type, and
runtime ID. Multiple matching owner spans are an explicit conflict and Studio
never selects the newest match. Applications do not receive a Studio API
credential to construct or follow these links.

### Database & Storage Access

#### Inspecting Parquet Files (Span Data)

The ingestion service stores spans in Parquet files. You can inspect them using Python.

```python
import pyarrow.parquet as pq

# Read cold tier
table = pq.read_table('.dbdata/spans/parquet/')
print(f"Cold tier spans: {table.num_rows}")

# Read hot snapshot
hot = pq.read_table('.dbdata/spans/hot_snapshot.parquet')
print(f"Hot tier spans: {hot.num_rows}")
```

#### Accessing SQLite (User Data)

The backend container exclusively owns the live SQLite database and its WAL
files. Use Studio's HTTP APIs while the stack is running; do not open the
bind-mounted database with a host SQLite process. Stop the complete stack before
offline maintenance. The greenfield reset and setup flow is documented in
`TESTING.md`.

### Performance Tuning

- **Ingestion throughput**: Adjust ingestion tunables in `.env` (see `.env.example`, e.g. `BATCH_SIZE`, `FLUSH_MAX_MB`, `FLUSH_MAX_AGE_SECS`, `BACKPRESSURE_MAX_MB`)
- **Database performance**: SQLite uses WAL mode for better concurrency
- **Container resources**: Increase memory limits if processing high span volumes

---

## Testing

Junjo AI Studio has comprehensive test coverage across all services. Tests are organized to support both local development and CI/CD pipelines.

### Quick Start: Run All Tests

```bash
# Run all tests (backend, ingestion, frontend, contract validation)
./run-all-tests.sh
```

This script runs:
0. **Proto version checking** - Warns if the system compiler used by Rust does not match v30.2
1. **Backend formatting and linting** - Runs `cargo fmt --check` and clippy on backend code
2. **Backend tests** - Rust tests for both backend crates; they build the ingestion binary
3. **Ingestion tests** - Rust unit/integration tests (Cargo)
4. **Frontend tests** - Unit, integration, and component tests (TypeScript/Vitest), then lint and the production build
5. **Contract tests** - Validates frontend ↔ backend API schema compatibility
6. **OpenAPI document validation** - Fails if the committed document is not what the backend exports

### Test Scripts Organization

**Run everything:**
- `./run-all-tests.sh` - Complete test suite for all services

**Backend-specific:**
- `cd backend && cargo test --locked` - All backend tests
- `./backend/scripts/validate_rest_api_contracts.sh` - Exports the OpenAPI document and runs the contract tests (schema validation)

**Frontend-specific:**
- `cd frontend && npm run test:run` - All frontend tests (exits after completion)
- `cd frontend && npm test` - Frontend tests in watch mode
- `cd frontend && npm run test:contracts` - Contract tests only

**Individual services:**
- Backend: See [backend/README.md](backend/README.md#commands) for commands and [TESTING.md](TESTING.md#backend-test-layers) for the test layers
- Frontend: See [TESTING.md](TESTING.md) for testing strategy and [frontend/README.md](frontend/README.md) for frontend commands
- Ingestion: See [ingestion/README.md](ingestion/README.md) for Rust tests

### Version Management

Junjo AI Studio uses a centralized root `VERSION` file for release/app metadata synchronization.

```bash
# Sync all managed version fields from VERSION
./scripts/sync-version.sh

# Set a new version and sync everything
./scripts/sync-version.sh 0.82.0

# Verify all managed files are in sync with VERSION
./scripts/check-version-sync.sh
```

Managed files include backend (`Cargo.toml`/`Cargo.lock`), ingestion (`Cargo.toml`/`Cargo.lock`), frontend (`package.json`/`package-lock.json`), and the exported OpenAPI document (`frontend/backend/openapi.json`).

Release guardrail: Docker publish workflow validates that the GitHub release tag exactly matches `VERSION`.

### Development Workflow & Validation

Understanding what each validation tool does helps avoid surprises at commit time.

#### What Each Tool Does

| Validation | run-all-tests.sh | pre-commit hook | CI (GitHub Actions) |
|------------|------------------|-----------------|---------------------|
| **Proto version check** | ✅ Warns | ❌ | ✅ Enforces |
| **Backend formatting (`cargo fmt --check`)** | ✅ Fails | ✅ Fails | ✅ Enforces |
| **Backend linting (clippy)** | ✅ Fails | ❌ | ✅ Enforces |
| **Backend tests** | ✅ Runs all | ❌ | ✅ Enforces |
| **Ingestion tests** | ✅ Runs all | ❌ | ✅ Enforces |
| **Frontend tests** | ✅ Runs all | ❌ | ✅ Enforces |
| **Contract tests** | ✅ Validates | ❌ | ✅ Enforces |
| **OpenAPI document staleness check** | ✅ Fails on diff | ❌ | ✅ Enforces |

#### Recommended Workflow

**During development (before committing):**

```bash
# Option 1: Run everything at once (recommended)
./run-all-tests.sh

# Option 2: Run individual validations (each from the Studio root)
(cd backend && cargo fmt --check)             # Formatting
(cd backend && cargo clippy --all-targets --locked -- -D warnings)  # Linting
(cd backend && cargo test --locked)           # Backend tests
(cd ingestion && cargo test --locked)         # Ingestion tests
(cd frontend && npm run test:run)             # Frontend tests
./backend/scripts/validate_rest_api_contracts.sh  # Contracts
```

**At commit time:**

```bash
git commit
# Pre-commit hook runs automatically (install it with ./scripts/install-git-hooks.sh):
# - Runs cargo fmt --check on the backend (blocks if formatting differs)
```

**Philosophy:**

- **run-all-tests.sh**: Comprehensive validation during development - catches issues early
- **pre-commit hook**: Safety net - keeps unformatted backend code out of commits
- **CI**: Final enforcement - prevents merging broken code

**Why run-all-tests.sh covers pre-commit:**

The pre-commit hook runs the same `cargo fmt --check` that run-all-tests.sh runs first.

**Result:** No surprises at commit time. If run-all-tests.sh passes, pre-commit will too.

### Contract Testing

Junjo AI Studio uses **contract testing** to prevent frontend/backend API drift. The backend's Rust request and response types are the single source of truth, validated against frontend TypeScript/Zod schemas using OpenAPI-generated mocks.

**How it works:**
1. The backend binary exports its OpenAPI document, generated from its Rust types and routes
2. Frontend tests generate mocks from OpenAPI spec
3. Zod schemas validate they can parse the mocks
4. Tests fail if schemas drift

**Run contract tests:**
```bash
./backend/scripts/validate_rest_api_contracts.sh
```

See [TESTING.md](TESTING.md#contract-testing-frontendbackend) for detailed documentation.

### GitHub Actions

These workflows run on pushes to `master` that touch their paths, and again in Studio release validation:
- `../../.github/workflows/studio-backend-tests.yml` - Backend tests, formatting, and linting; ingestion tests
- `../../.github/workflows/studio-rest-api-contract-validation.yml` - REST API contract tests and the committed OpenAPI document
- `../../.github/workflows/studio-version-sync-check.yml` - Version drift validation against `VERSION`

---

## Troubleshooting

### Session Cookie / Authentication Issues

**Symptom**: Can't sign in, or immediately signed out after login.

**Causes & Solutions:**

1. **Multiple Junjo instances on localhost**
   - Old session cookies from another instance may interfere
   - **Fix**: Clear browser cookies for `localhost` and restart services

2. **Studio served over plain HTTP in production**
   - With `JUNJO_ENV=production` the session cookie is `Secure`, so the browser sends it only over HTTPS
   - **Fix**: Serve the Studio hostname over HTTPS (see [Deployment Requirements](#deployment-requirements))

Hosted deployment troubleshooting lives with the deployment stack you choose. For working examples, start from the minimal-build or deployment-example repositories.

### Port Conflicts

**Symptom**: `Error: bind: address already in use`

**Solution:**
```bash
# Find process using the port
lsof -i :26151  # or :26154, :26155, etc.

# Kill the process
kill -9 <PID>
```

### Container Startup Issues

**Symptom**: Services fail to start or health checks fail

**Solutions:**

1. **Check logs**
   ```bash
   docker compose logs backend
   docker compose logs ingestion
   docker compose logs frontend   # development profile only
   ```

2. **Clear volumes and rebuild**
   ```bash
   docker compose down -v
   docker compose up --build
   ```

3. **Check .env file**
   - Ensure all required variables are set
   - `JUNJO_INTERNAL_GRPC_TOKEN` must be at least 32 characters
   - With `JUNJO_ENV=production`, `JUNJO_PROD_INGESTION_URL` must be set

### Database Issues

**Symptom**: Database errors or corruption warnings, or the backend refuses to start because `junjo.db` has another schema version

**Solution:**
```bash
# Stop services
docker compose down

# Backup and clear database files
mv .dbdata .dbdata.backup

# Restart (will create fresh databases)
docker compose up --build
```

---

## Resources

### Documentation
- **[Junjo Python Library](https://github.com/mdrideout/junjo/tree/master/sdks/python)** - explicit Workflow and bounded Agent execution framework

### Deployment Distributions

- **[Canonical minimal source](deployments/minimal)** — minimal setup with
  pre-built images; also published as the
  [minimal-build mirror](https://github.com/mdrideout/junjo-ai-studio-minimal-build).
- **[Canonical VM/Caddy source](deployments/vm-caddy)** — complete VM example
  with one reverse-proxy implementation; also published as the
  [deployment-example mirror](https://github.com/mdrideout/junjo-ai-studio-deployment-example).

### Docker Hub Images
- **[junjo-ai-studio-app](https://hub.docker.com/r/mdrideout/junjo-ai-studio-app)** - Studio application: Rust backend API and the React web UI
- **[junjo-ai-studio-ingestion](https://hub.docker.com/r/mdrideout/junjo-ai-studio-ingestion)** - Rust gRPC ingestion service

### OpenTelemetry Resources
- **[OpenTelemetry Documentation](https://opentelemetry.io/docs/)** - OTLP specification
- **[OpenTelemetry Python](https://opentelemetry-python.readthedocs.io/)** - Python SDK

---

**Junjo AI Studio** - Making AI Workflow and Agent executions transparent and understandable.

Copyright (C) 2025 Matthew Rideout

Junjo-authored Studio source is licensed under the Apache License, Version 2.0.
See [`LICENSE`](LICENSE). Incorporated third-party source and historical
provenance are documented in
[`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md).

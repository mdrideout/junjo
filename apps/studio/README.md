# Junjo AI Studio

> Junjo (順序) - order, sequence, procedure

**Junjo AI Studio** is an open source, self-hostable AI Agent and Workflow debugging and eval platform for any OpenTelemetry instrumented AI application. 

The [Junjo Python Library](https://github.com/mdrideout/junjo) is a framework for structuring AI logic and enhancing Otel span data to improve observability and developer velocity. Junjo remains decoupled from your LLM implemetations and business logic, proving a layer of orgnization, execution, and telemetry to your existing application.

Gain complete visibility to the state of the application, and every change LLMs make to the application state. Complex, mission critical AI workflows are made transparent and understandable with Junjo.

<img src="https://python-api.junjo.ai/_images/junjo-screenshot.png" width="800" />

_Junjo AI Studio Workflow Debugging Screenshot_

### Key Features

- 🔍 **Real-time LLM Decision Visibility** - See every decision your LLM makes and the data it uses
- 🔀 **Transparent Concurrency** - Debug state changes from concurrently executed AI workflow steps
- 📊 **OpenTelemetry Native** - Standards-based telemetry ingestion via gRPC
- 🎯 **Workflow Debugging Interface** - Visual step-by-step debugging of AI graph workflows
- 🪶 **Prompt Playground** - Expirement with different models and prompt tweaks while you debug
- 🔒 **Production-Ready Security** - Authentication, user accounts, and encrypted sessions
- 🚀 **Low Resource, High-Performance Ingestion** - Designed for high-throughput in low resource environments
- 💾 **Shared vCPU, 1GB Ram** - Production grade telemetry on a $5 / month virutal machine

---

## Table of Contents

- [Quick Start](#quick-start)
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

Get Junjo AI Studio running on your local machine in 5 minutes using the **[Junjo AI Studio Bare Bones](https://github.com/mdrideout/junjo-server-bare-bones)** repository. This repository provides a minimal, standalone setup using pre-built Docker images from Docker Hub, perfect for both quick testing and production deployments of Junjo AI Studio.

### Steps

1. **Clone the bare-bones repository**
   ```bash
   git clone https://github.com/mdrideout/junjo-server-bare-bones.git
   cd junjo-server-bare-bones
   ```

2. **Copy the environment configuration**
   ```bash
   cp .env.example .env
   ```

3. **Generate security secrets**
   ```bash
   # Generate session secret (copy this output)
   openssl rand -base64 32

   # Generate secure cookie key (copy this output)
   openssl rand -base64 32
   ```

   Open `.env` in a text editor and replace the placeholder values:
   - Replace `your_base64_secret_here` in `JUNJO_SESSION_SECRET` with the first generated value
   - Replace `your_base64_key_here` in `JUNJO_SECURE_COOKIE_KEY` with the second generated value

   _See the [Bare Bones template repository](https://github.com/mdrideout/junjo-server-bare-bones/blob/master/README.md) for in-depth configuration instructions._
 
4. **Create the Docker network** (first time only)
   ```bash
   docker network create junjo-network
   ```

5. **Start all services**
   ```bash
   docker compose up -d
   ```

6. **Access Junjo AI Studio**
   - **Frontend**: http://localhost:5153
   - **Backend API**: http://localhost:1323
   - **OTLP Ingestion Endpoint**: grpc://localhost:50051

7. **Create your first user**
   - Navigate to http://localhost:5153
   - Follow the setup wizard to create your admin account

8. **Create an API key** (for sending telemetry from your Junjo app)
   - Sign in to the web UI
   - Navigate to **Settings → API Keys**
   - Click **Create API Key**
   - Copy the 64-character key (shown only once)
   - Use this key in your Junjo Python Library application

### Useful Docker Compose Commands

```bash
# View logs from all services
docker compose logs -f

# View logs from specific service
docker compose logs -f junjo-server-backend
docker compose logs -f junjo-server-ingestion
docker compose logs -f junjo-server-frontend

# Stop services (keeps data)
docker compose down

# Restart a specific service
docker compose restart junjo-server-backend

# View running containers and their status
docker compose ps

# Stop and remove all data (fresh start)
docker compose down -v
```

### Next Steps

Configure your [Junjo Python Library](https://github.com/mdrideout/junjo) application to send telemetry to `grpc://localhost:50051` using the API key you created.

**For source code development**: If you want to modify Junjo AI Studio's source code (not just use it), see the development guides in `backend/README.md`, `frontend/README.md`, and `ingestion/README.md` in the main [junjo-server repository](https://github.com/mdrideout/junjo-server).

---

## Features

### What Can You Do With Junjo AI Studio?

**Observability & Debugging:**
- View complete execution traces of AI workflows
- Inspect LLM prompts, responses, and reasoning
- Track state changes across workflow nodes
- Monitor performance and latency

**LLM Playground:**
- Test prompts with multiple providers (OpenAI, Anthropic, Google Gemini)
- Compare responses across models
- Experiment with temperature and reasoning modes

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

The Junjo AI Studio is composed of three primary services:

### 1. Backend (`junjo-server-backend`)
- **Tech Stack**: FastAPI (Python), SQLite, DuckDB
- **Responsibilities**:
  - HTTP REST API
  - User authentication & session management
  - LLM playground
  - Span querying & analytics

### 2. Ingestion Service (`junjo-server-ingestion`)
- **Tech Stack**: Go, gRPC, BadgerDB
- **Responsibilities**:
  - OpenTelemetry OTLP/gRPC endpoint (port 50051)
  - High-throughput span ingestion
  - Durable Write-Ahead Log (WAL) with BadgerDB

### 3. Frontend (`junjo-server-frontend`)
- **Tech Stack**: React, TypeScript
- **Responsibilities**:
  - Web UI for workflow visualization
  - LLM playground interface
  - User management

**Data Flow:**
```
Junjo Python App → Ingestion Service (gRPC) → BadgerDB WAL
                                                    ↓
Backend Service ← polls for new spans ← BadgerDB WAL
       ↓
    DuckDB (analytics)
    SQLite (metadata)
       ↓
    Frontend UI
```

The `backend` service polls the `ingestion`'s internal gRPC API to read batches of spans from the WAL, which it then indexes into DuckDB for analytics queries.

---

## Prerequisites

### Required
- **Docker** and **Docker Compose** (for both development and production)

### Optional (Development)
- **Go 1.21+** (for ingestion service development)
- **Python 3.13+** with **uv** (for backend development)
- **Node.js 18+** (for frontend development)
- **BadgerDB CLI** (for database inspection)

### For Production Deployment
- A domain or subdomain for hosting (see [Deployment Requirements](#deployment-requirements))
- SSL certificates (automatic with Caddy, Let's Encrypt, etc.)

---

## Configuration

### Environment Variables

Junjo AI Studio uses a single `.env` file at the root of the project. All services read from this file.

#### Key Configuration Variables

```bash
# === Build & Environment ===========================================
# Build Target: development | production
JUNJO_BUILD_TARGET="development"

# Running Environment: development | production
# (affects cookie security, logging, etc.)
JUNJO_ENV="development"

# === Security (REQUIRED for production) ============================
# Generate both with: openssl rand -base64 32
JUNJO_SESSION_SECRET=your_base64_secret_here
JUNJO_SECURE_COOKIE_KEY=your_base64_key_here

# === CORS ==========================================================
# Comma-separated list of allowed origins
JUNJO_ALLOW_ORIGINS=http://localhost:5151,http://localhost:5153

# === Ports =========================================================
PORT=1323                    # Backend HTTP port
INGESTION_PORT=50051        # OTLP ingestion gRPC port (public)
GRPC_PORT=50053             # Backend internal gRPC port

# === Database Storage ==============================================
# Host storage location (where database files are stored on host machine)
HOST_DB_DATA_PATH=./.dbdata

# Container paths (where apps look for databases inside containers)
DB_SQLITE_PATH=/dbdata/sqlite/junjo.db
DB_DUCKDB_PATH=/dbdata/duckdb/traces.duckdb
BADGERDB_PATH=/dbdata/badgerdb

# === Logging =======================================================
LOG_LEVEL=info              # debug | info | warn | error
LOG_FORMAT=text             # json | text

# === LLM API Keys (optional) =======================================
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
GEMINI_API_KEY=...
```

**See `.env.example` for complete configuration with detailed comments.**

### Database Storage Configuration

Junjo AI Studio uses a **two-layer system** for database storage that separates host machine paths from container paths:

#### Understanding the Two Layers

1. **`HOST_DB_DATA_PATH`** - Where files are stored on your **host machine**
2. **`DB_*_PATH` variables** - Where applications look **inside Docker containers**

Docker mounts `HOST_DB_DATA_PATH` from your host to `/app/.dbdata` inside containers, making database files accessible to all services.

#### Development Setup

For local development, use a relative path:

```bash
# .env file
HOST_DB_DATA_PATH=./.dbdata
JUNJO_BUILD_TARGET=development
```

This stores databases in `./.dbdata` directory next to your `docker-compose.yml`. Docker creates this directory automatically.

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
HOST_DB_DATA_PATH=/mnt/junjo-data
JUNJO_BUILD_TARGET=production
```

**3. Start services:**
```bash
docker compose up -d
```

**Benefits:**
- Data persists across container restarts
- Data survives even if you delete and recreate containers
- Easy to backup by snapshotting the volume
- Can detach and reattach to different instances

#### Important Notes

- **Container paths** (`DB_SQLITE_PATH`, `DB_DUCKDB_PATH`, `BADGERDB_PATH`) should **not be changed** unless you modify the Dockerfiles
- The `HOST_DB_DATA_PATH` variable works in `docker-compose.yml` through variable substitution: `${HOST_DB_DATA_PATH:-./.dbdata}`
- If `HOST_DB_DATA_PATH` is not set, it defaults to `./.dbdata`
- All three services (backend, ingestion, frontend) share the same storage location

#### Database Types

Junjo AI Studio uses three embedded databases:

| Database | Purpose | Type |
|----------|---------|------|
| **SQLite** | User data, API keys, sessions | Single file |
| **DuckDB** | Analytics queries on telemetry | Single file |
| **BadgerDB** | Ingestion WAL (Write-Ahead Log) | Directory with multiple files |

All are stored under `HOST_DB_DATA_PATH` on your host machine.

### Creating API Keys

After starting Junjo AI Studio:
1. Sign in to the web UI (http://localhost:5153)
2. Navigate to **Settings → API Keys**
3. Click **Create API Key**
4. Copy the 64-character key (shown only once)
5. Use this key in your Junjo Python Library application

---

## Production Deployment

### Deployment Requirements

⚠️ **IMPORTANT**: The backend API and frontend **MUST be deployed on the same domain** (sharing the same registrable domain).

**Supported configurations:**
- ✅ `api.example.com` + `app.example.com` (subdomain + subdomain)
- ✅ `api.example.com` + `example.com` (subdomain + apex)
- ✅ `example.com` + `api.example.com` (apex + subdomain)
- ❌ `app.example.com` + `service.run.app` (different domains - **will NOT work**)

**Why?** Junjo AI Studio uses session cookies with `SameSite=Strict` for security (CSRF protection). Cross-domain deployments will cause authentication to fail.

**📖 See [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) for complete deployment guide**, including:
- Platform-specific examples (Google Cloud Run, AWS, Docker Compose)
- Environment configuration for production
- Security features and best practices
- Troubleshooting guide

### Turn-Key Example Repositories

#### Junjo AI Studio Bare Bones
**[https://github.com/mdrideout/junjo-server-bare-bones](https://github.com/mdrideout/junjo-server-bare-bones)**

A minimal, standalone repository with just the core Junjo AI Studio components using pre-built Docker images.

**Best for:**
- Quick testing of Junjo AI Studio
- Simple production deployments
- Integration into existing infrastructure

#### Junjo AI Studio Deployment Example
**[https://github.com/mdrideout/junjo-server-deployment-example](https://github.com/mdrideout/junjo-server-deployment-example)**

A complete, production-ready example that includes a Junjo Python Library application alongside the server infrastructure.

**Best for:**
- End-to-end deployment examples
- Learning how to configure your Junjo app with the server
- VM deployment guide (Digital Ocean Droplet, AWS EC2, etc.)
- Caddy reverse proxy setup for SSL

The [README](https://github.com/mdrideout/junjo-server-deployment-example/blob/master/README.md) provides step-by-step deployment instructions.

### Docker Compose - Production Images

Junjo AI Studio is built and deployed to **Docker Hub** with each GitHub release:

- **Backend**: [mdrideout/junjo-server-backend](https://hub.docker.com/r/mdrideout/junjo-server-backend)
- **Ingestion Service**: [mdrideout/junjo-server-ingestion](https://hub.docker.com/r/mdrideout/junjo-server-ingestion)
- **Frontend**: [mdrideout/junjo-server-frontend](https://hub.docker.com/r/mdrideout/junjo-server-frontend)

**Example docker-compose.yml:**

```yaml
services:
  junjo-server-backend:
    image: mdrideout/junjo-server-backend:latest
    container_name: junjo-server-backend
    restart: unless-stopped
    volumes:
      - ${HOST_DB_DATA_PATH:-./.dbdata}:/app/.dbdata
    ports:
      - "1323:1323"   # HTTP API (public)
      # Port 50053 (internal gRPC for API key validation) is NOT exposed - only accessible via Docker network
    networks:
      - junjo-network
    env_file:
      - .env
    environment:
      - INGESTION_HOST=junjo-server-ingestion
      - INGESTION_PORT=50052
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:1323/ping"]
      interval: 5s
      timeout: 3s
      retries: 25
      start_period: 5s

  junjo-server-ingestion:
    image: mdrideout/junjo-server-ingestion:latest
    container_name: junjo-server-ingestion
    restart: unless-stopped
    volumes:
      - ${HOST_DB_DATA_PATH:-./.dbdata}:/app/.dbdata
    ports:
      - "50051:50051"  # Public OTLP endpoint (authenticated via API key)
      # Port 50052 (internal gRPC for span reading) is NOT exposed - only accessible via Docker network
    networks:
      - junjo-network
    env_file:
      - .env
    environment:
      - BACKEND_GRPC_HOST=junjo-server-backend
      - BACKEND_GRPC_PORT=50053
    depends_on:
      junjo-server-backend:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "grpc_health_probe", "-addr=localhost:50052"]
      interval: 5s
      timeout: 3s
      retries: 5
      start_period: 5s

  junjo-server-frontend:
    image: mdrideout/junjo-server-frontend:latest
    container_name: junjo-server-frontend
    restart: unless-stopped
    ports:
      - "5153:80"
    env_file:
      - .env
    networks:
      - junjo-network
    depends_on:
      junjo-server-backend:
        condition: service_healthy
      junjo-server-ingestion:
        condition: service_healthy

networks:
  junjo-network:
    driver: bridge
```

For a more complete example with reverse proxy, see the [Junjo AI Studio Deployment Example Repository](https://github.com/mdrideout/junjo-server-deployment-example/blob/master/docker-compose.yml).

### VM Resource Requirements

Junjo AI Studio is designed to be low resource:
- **Minimum**: Shared vCPU + 1GB RAM
- **Databases**: SQLite, DuckDB, BadgerDB (all embedded, low overhead)
- **Recommended**: 1 vCPU + 2GB RAM for production workloads

---

## Advanced Topics

### Database Access

#### Inspecting BadgerDB

BadgerDB is the Write-Ahead Log for ingested spans. You can inspect it using the BadgerDB CLI.

**Install BadgerDB CLI:**
```bash
go install github.com/dgraph-io/badger/v4/badger@latest
```

**Inspect data:**
```bash
# Read the database (requires ingestion service to be stopped)
badger stream --dir ./.dbdata/badgerdb

# Read with cleanup (use if database wasn't shut down properly)
badger stream --dir ./.dbdata/badgerdb --read_only=false
```

**Note**: BadgerDB is a directory-based database that creates multiple files (`value log`, `manifest`, etc.), unlike SQLite/DuckDB which are single-file databases.

#### Accessing SQLite and DuckDB

```bash
# SQLite (user data, API keys)
sqlite3 ./.dbdata/sqlite/junjo.db

# DuckDB (span analytics)
duckdb ./.dbdata/duckdb/traces.duckdb
```

### Performance Tuning

- **Ingestion throughput**: Adjust `SPAN_BATCH_SIZE` and `SPAN_POLL_INTERVAL` in `.env`
- **Database performance**: DuckDB and SQLite use WAL mode for better concurrency
- **Container resources**: Increase memory limits if processing high span volumes

---

## Testing

Junjo AI Studio has comprehensive test coverage across all services. Tests are organized to support both local development and CI/CD pipelines.

### Quick Start: Run All Tests

```bash
# Run all tests (backend, frontend, contract validation, proto validation)
./run-all-tests.sh
```

This script runs:
1. **Backend tests** (unit, integration, gRPC) - Python/pytest
2. **Frontend tests** (unit, integration, component) - TypeScript/Vitest
3. **Contract tests** (API schema validation) - Validates frontend ↔ backend compatibility
4. **Proto validation** - Ensures protobuf files are up-to-date

### Test Scripts Organization

**Run everything:**
- `./run-all-tests.sh` - Complete test suite for all services

**Backend-specific:**
- `./backend/scripts/run-backend-tests.sh` - All backend tests (unit, integration, gRPC)
- `./backend/scripts/ci_validate_schemas.sh` - Contract tests (schema validation)

**Frontend-specific:**
- `cd frontend && npm run test:run` - All frontend tests (exits after completion)
- `cd frontend && npm test` - All frontend tests (watch mode)
- `cd frontend && npm run test:contracts` - Contract tests only

**Individual services:**
- Backend: See [backend/README.md](backend/README.md#testing) for detailed test categories
- Frontend: See [frontend/README.md](frontend/README.md) for component testing
- Ingestion: See [ingestion/README.md](ingestion/README.md) for Go tests

### Contract Testing

Junjo AI Studio uses **contract testing** to prevent frontend/backend API drift. Backend Pydantic schemas are the single source of truth, validated against frontend TypeScript/Zod schemas using OpenAPI-generated mocks.

**How it works:**
1. Backend exports OpenAPI schema from Pydantic models
2. Frontend tests generate mocks from OpenAPI spec
3. Zod schemas validate they can parse the mocks
4. Tests fail if schemas drift

**Run contract tests:**
```bash
./backend/scripts/ci_validate_schemas.sh
```

See [backend/scripts/README_SCHEMA_VALIDATION.md](backend/scripts/README_SCHEMA_VALIDATION.md) for detailed documentation.

### GitHub Actions

Tests run automatically on all PRs via GitHub Actions:
- `.github/workflows/backend-tests.yml` - Backend test suite
- `.github/workflows/schema-validation.yml` - Contract tests
- `.github/workflows/validate-proto.yml` - Proto file validation

---

## Troubleshooting

### Session Cookie / Authentication Issues

**Symptom**: Can't sign in, or immediately signed out after login.

**Causes & Solutions:**

1. **Multiple Junjo instances on localhost**
   - Old session cookies from another instance may interfere
   - **Fix**: Clear browser cookies for `localhost` and restart services

2. **Cross-domain deployment** (most common in production)
   - Frontend and backend on different top-level domains
   - **Fix**: Ensure both services share the same registrable domain (see [Deployment Requirements](#deployment-requirements))

3. **Missing or invalid secrets**
   - `JUNJO_SESSION_SECRET` or `JUNJO_SECURE_COOKIE_KEY` not set correctly
   - **Fix**: Generate new secrets with `openssl rand -base64 32`

4. **CORS misconfiguration**
   - Frontend URL not in `JUNJO_ALLOW_ORIGINS`
   - **Fix**: Add your frontend URL to the CORS origins list

**See [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md#troubleshooting) for detailed troubleshooting guide.**

### Port Conflicts

**Symptom**: `Error: bind: address already in use`

**Solution:**
```bash
# Find process using the port
lsof -i :1323  # or :50051, :5153, etc.

# Kill the process
kill -9 <PID>

# Or change the port in .env
PORT=1324
```

### Container Startup Issues

**Symptom**: Services fail to start or health checks fail

**Solutions:**

1. **Check logs**
   ```bash
   docker compose logs backend
   docker compose logs ingestion
   docker compose logs frontend
   ```

2. **Ensure network exists**
   ```bash
   docker network create junjo-network
   ```

3. **Clear volumes and rebuild**
   ```bash
   docker compose down -v
   docker compose up --build
   ```

4. **Check .env file**
   - Ensure all required variables are set
   - Secrets must be base64-encoded 32-byte values

### Database Issues

**Symptom**: Database errors or corruption warnings

**Solution:**
```bash
# Stop services
docker compose down

# Backup and clear database files
mv .dbdata .dbdata.backup

# Restart (will create fresh databases)
docker compose up
```

---

## Resources

### Documentation
- **[Deployment Guide](docs/DEPLOYMENT.md)** - Complete production deployment instructions
- **[Junjo Python Library](https://github.com/mdrideout/junjo)** - AI Graph Workflow framework

### Example Repositories
- **[Junjo AI Studio Bare Bones](https://github.com/mdrideout/junjo-server-bare-bones)** - Minimal setup with pre-built images
- **[Junjo AI Studio Deployment Example](https://github.com/mdrideout/junjo-server-deployment-example)** - Complete production deployment with Caddy

### Docker Hub Images
- **[junjo-server-backend](https://hub.docker.com/r/mdrideout/junjo-server-backend)** - FastAPI backend
- **[junjo-server-ingestion](https://hub.docker.com/r/mdrideout/junjo-server-ingestion)** - Go gRPC ingestion service
- **[junjo-server-frontend](https://hub.docker.com/r/mdrideout/junjo-server-frontend)** - React frontend

### OpenTelemetry Resources
- **[OpenTelemetry Documentation](https://opentelemetry.io/docs/)** - OTLP specification
- **[OpenTelemetry Python](https://opentelemetry-python.readthedocs.io/)** - Python SDK

---

**Junjo AI Studio** - Making AI workflows transparent and understandable.

Copyright (C) 2025 Matthew Rideout

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU Affero General Public License as
published by the Free Software Foundation, either version 3 of the
License, or (at your option) any later version.
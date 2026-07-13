# Junjo AI Studio - Minimal Build

> **Source and distribution:** The canonical source for this distribution is
> [`apps/studio/deployments/minimal`](https://github.com/mdrideout/junjo/tree/master/apps/studio/deployments/minimal)
> in the Junjo platform monorepo. The standalone
> [`junjo-ai-studio-minimal-build`](https://github.com/mdrideout/junjo-ai-studio-minimal-build)
> repository is the designated release mirror for convenient cloning. Its
> first monorepo-driven refresh remains a cutover gate. Submit changes to the
> canonical source; direct mirror changes will be overwritten after that
> publication path is active.

A minimal, opinionless Docker Compose setup for [Junjo AI Studio](https://github.com/mdrideout/junjo/tree/master/apps/studio) containing only the essential services. This minimal foundation provides the three core services needed to run Junjo AI Studio, with zero opinions about reverse proxies, networking, or infrastructure choices.

This template pins Junjo AI Studio `0.81.3`. Applications that emit Junjo workflow telemetry should use Junjo `0.63.0`.

A Junjo AI Studio instance can be used for an unlimited number of projects that use the [Junjo](https://github.com/mdrideout/junjo) python AI graph workflow framework. Any Junjo Application can send telemetry to this Junjo AI Studio instance, assuming it has valid API Key credentials.

> #### Full E2E Junjo Application Example:
>
>To see a full end-to-end opinionated deployment guide for a fresh Digital Ocean virtual machine, that includes a python application that uses the Junjo library to execute a graph workflow and sends telemetry to Junjo AI Studio, see this [Junjo AI Studio Deployment Example](https://github.com/mdrideout/junjo-ai-studio-deployment-example).

## What This Is

This is a **minimal build** template containing only the three essential Junjo AI Studio services:

**What's Included:**
- ✅ Three core services (backend, ingestion, frontend)
- ✅ Basic Docker Compose configuration
- ✅ Environment variable examples
- ✅ Reference configurations in `/examples`

**What's NOT Included (by design):**
- ❌ No reverse proxy (bring your own - Caddy, Nginx, Traefik, etc.)
- ❌ No SSL/TLS configuration (configure for your domain)
- ❌ No demo applications (focus on infrastructure only)
- ❌ No opinionated networking decisions (adapt to your setup)

**Perfect For:**
- Starting point for custom deployments
- Understanding Junjo AI Studio architecture
- Local development environments
- Integration into existing infrastructure
- Incorporating into an existing docker-compose.yml

**Use the [Junjo AI Studio Deployment Example](https://github.com/mdrideout/junjo-ai-studio-deployment-example) if you want:**
- Bundled reverse proxy (Caddy)
- Turn-key virtual mchine configuration deployment instructions
- Ready to accept custom domain names with SSL connections
- A demo application included for testing your production deployment
- Opinionated best practices

## Table of Contents

- [Junjo AI Studio - Minimal Build](#junjo-ai-studio---minimal-build)
	- [What This Is](#what-this-is)
	- [Table of Contents](#table-of-contents)
	- [Architecture](#architecture)
		- [Data Flow](#data-flow)
	- [Quick Start](#quick-start)
	- [Deployment Scenarios](#deployment-scenarios)
		- [Scenario 1: Same VM/Network (No Reverse Proxy)](#scenario-1-same-vmnetwork-no-reverse-proxy)
		- [Scenario 2: External Access (Reverse Proxy Required)](#scenario-2-external-access-reverse-proxy-required)
		- [Scenario 3: Cloud Platform Deployments](#scenario-3-cloud-platform-deployments)
			- [Render](#render)
			- [Railway](#railway)
	- [Reverse Proxy Configuration](#reverse-proxy-configuration)
	- [Junjo Application Telemetry Configuration](#junjo-application-telemetry-configuration)
		- [Full Example](#full-example)
	- [Troubleshooting](#troubleshooting)
		- [Session Cookie Issues](#session-cookie-issues)
		- [Port Conflicts](#port-conflicts)
		- [Checking Logs](#checking-logs)
	- [License](#license)

## Architecture

Junjo AI Studio consists of three Docker services:

- **junjo-ai-studio-frontend**
  - **Web UI Port:** 26153
  - Web UI for viewing and debugging workflows
  - Served at the root domain (e.g., `https://junjo.example.com`)

- **junjo-ai-studio-backend**
  - **HTTP API Port:** 26154
  - **Internal Port:** 50053 (gRPC for API key validation - Docker network only)
  - HTTP API server for authentication and data queries
  - Uses SQLite for application data and metadata indexing
  - Queries cold Parquet telemetry and merges with ingestion hot snapshots
  - Served at the API subdomain (e.g., `https://api.junjo.example.com`)

- **junjo-ai-studio-ingestion**
  - **OTLP gRPC Port:** 26155
  - **Internal Port:** 50052 (gRPC for span reading - Docker network only)
  - High-throughput gRPC service for receiving OpenTelemetry data
  - Uses Arrow IPC WAL segments and flushes to Parquet for durable cold storage
  - Provides internal gRPC for hot snapshot preparation
  - Your Python applications send telemetry to this service (e.g., `https://grpc.junjo.example.com`)

**Security Note:** Internal ports (50052, 50053) are only accessible within the Docker network and are not exposed to the host machine. This ensures secure service-to-service communication.

### Data Flow

1. Python applications → **Ingestion Service** (OTLP gRPC on port 26155)
2. Ingestion Service → Arrow IPC WAL segments → flushes to Parquet
3. Backend → Calls ingestion internal gRPC (port 50052) for hot snapshots
4. Backend → Uses SQLite metadata index + Parquet files for trace queries
5. Frontend → Queries backend API → User views data

## Quick Start

**Local Development Setup** (runs on localhost, no reverse proxy needed):

1. Clone this repository:
   ```bash
   git clone https://github.com/mdrideout/junjo-ai-studio-minimal-build.git
   cd junjo-ai-studio-minimal-build
   ```

2. Choose setup mode:

   **Option A: Guided setup script (recommended)**
   ```bash
   ./scripts/junjo setup
   ```
   The wizard prompts for runtime environment:
   - `development` uses localhost ports and service endpoints
   - `production` asks for your production hostname and derives frontend/backend/ingestion URLs
   - It also applies a memory profile and generates required secrets
   - At completion, it prints the frontend/backend/ingestion URLs and ports

   **Option B: Manual setup**
   ```bash
   cp .env.example .env
   ```
   Then generate and set secrets:
   ```bash
   # Generate TWO separate keys (run this command twice)
   openssl rand -base64 32
   openssl rand -base64 32

   # Edit .env and replace:
   # - JUNJO_SESSION_SECRET with the first generated value
   # - JUNJO_SECURE_COOKIE_KEY with the second generated value
   ```

3. Start services:
   ```bash
   docker compose up -d
   ```
   > Note: Docker Compose creates a project-scoped network automatically. Do not create or share a network manually.

4. Access the frontend:
   - **Frontend UI:** `http://localhost:26153`
     - _Troubleshooting: Try clearing your cookies if you encounter issues._
   - Create your first API key in the UI

5. Configure your Junjo Python application's exporter:
   ```python
   from junjo.telemetry.junjo_otel_exporter import JunjoOtelExporter

   junjo_exporter = JunjoOtelExporter(
       host="localhost",
       port="26155",
       api_key=JUNJO_AI_STUDIO_API_KEY,
       insecure=True,
   )
   ```

**Note:** This repository always uses pre-built production Docker images from Docker Hub and does not use a `JUNJO_BUILD_TARGET` variable. For production runtime routing with a reverse proxy, set `JUNJO_ENV="production"` and provide production hostnames (the setup script can do this automatically).

For a complete working example with reverse proxy included, see the [Junjo AI Studio Deployment Example](https://github.com/mdrideout/junjo-ai-studio-deployment-example).

## Deployment Scenarios

Choose the deployment scenario that matches your infrastructure:

### Scenario 1: Same VM/Network (No Reverse Proxy)

**Use this when:**
- Your Junjo application and Junjo AI Studio run on the same virtual machine
- Services share a Docker network or VPC
- You don't need external services to send telemetry to Junjo AI Studio

**Benefits:**
- Simpler setup - no reverse proxy configuration needed
- Direct container-to-container communication
- Lower latency
- No SSL/TLS overhead

**Access:**
- Frontend: `http://localhost:26153` (or the VM's IP address)
- Your application connects directly to `junjo-ai-studio-ingestion:26155` on the Docker network

**Python Configuration:**
```python
junjo_exporter = JunjoOtelExporter(
    host="junjo-ai-studio-ingestion",  # Docker service name
    port="26155",                       # OTLP gRPC port
    api_key=JUNJO_AI_STUDIO_API_KEY,
    insecure=True,                      # No TLS needed on internal network
)
```

### Scenario 2: External Access (Reverse Proxy Required)

**Use this when:**
- Your Junjo application runs on a different server/cloud than Junjo AI Studio
- You need multiple external services to send telemetry to Junjo AI Studio
- You want HTTPS/TLS for secure communication

**Benefits:**
- Centralized Junjo AI Studio for multiple applications
- Secure HTTPS/TLS communication
- Professional domain-based URLs
- Can be accessed from anywhere

**Requirements:**
- Reverse proxy (Caddy, Nginx, or Traefik)
- Domain name with DNS configured
- SSL/TLS certificates (can be automated with Let's Encrypt)

**Access:**
- Frontend: `https://junjo.example.com`
- Backend API: `https://api.junjo.example.com`
- Ingestion gRPC: `https://ingestion.junjo.example.com`

**Python Configuration:**
```python
junjo_exporter = JunjoOtelExporter(
    host="ingestion.junjo.example.com",   # Your domain
    port="443",                       		# HTTPS port
    api_key=JUNJO_AI_STUDIO_API_KEY,
    insecure=False,                   		# TLS enabled
)
```

### Scenario 3: Cloud Platform Deployments

**Use this when:**
- You want managed infrastructure without VM management
- Automatic SSL/TLS and domain routing
- Container orchestration handled for you
- Scalability and monitoring built-in

**Overview:**
Modern cloud platforms (Render, Railway) can host Junjo AI Studio's three services as separate containers with managed infrastructure. These platforms handle SSL/TLS, load balancing, and networking automatically.

**Key Considerations:**
- **Three separate services:** Each Junjo AI Studio service (backend, ingestion, frontend) deploys independently
- **Persistent volumes:** Required for SQLite and spans storage (WAL/snapshots/Parquet)
- **Internal networking:** Services must communicate via internal URLs
- **Environment variables:** Configure `JUNJO_ENV="production"` along with `JUNJO_PROD_FRONTEND_URL`, `JUNJO_PROD_BACKEND_URL`, and `JUNJO_PROD_INGESTION_URL`
- **Cost:** Running 3 services simultaneously (check platform pricing)

---

#### Render

**Best For:** Teams wanting a Heroku-like experience with more flexibility

**Deployment Approach:**
- Create 3 separate "Web Services" from the Docker images:
  - `mdrideout/junjo-ai-studio-backend:0.81.3`
  - `mdrideout/junjo-ai-studio-ingestion:0.81.3`
  - `mdrideout/junjo-ai-studio-frontend:0.81.3`
- Add persistent disks for data volumes

**Volume Configuration:**
```
Backend Service:
├─ /app/.dbdata/sqlite (SQLite app + metadata databases)
└─ /app/.dbdata/spans (Parquet cold data + hot snapshot access)

Ingestion Service:
└─ /app/.dbdata/spans (WAL, hot snapshot, and Parquet output)
```

**Internal Networking:**
- Services communicate via Render's internal network
- Backend connects to ingestion via the private `junjo-ai-studio-ingestion:50052` RPC
- Frontend connects to backend via: `http://junjo-ai-studio-backend:26154`

**Environment Setup:**
```bash
JUNJO_ENV=production
JUNJO_PROD_FRONTEND_URL=https://app.your-domain.com
JUNJO_PROD_BACKEND_URL=https://api.your-domain.com
JUNJO_PROD_INGESTION_URL=https://ingestion.your-domain.com
JUNJO_SESSION_SECRET=<generated-secret>
JUNJO_SECURE_COOKIE_KEY=<generated-secret>
```

**Public Access:**
- Render provides automatic HTTPS
- Custom domain supported
- Example: `https://junjo.yourapp.onrender.com`

**Resources:**
- [Render Docker Deployment Guide](https://render.com/docs/docker)
- [Render Persistent Disks](https://render.com/docs/disks)

---

#### Railway

**Best For:** Rapid prototyping and hobby projects with simple pricing

**Deployment Approach:**
- Create a new project in Railway dashboard
- Deploy 3 services from Docker images
- Add volumes for persistence
- Railway handles networking automatically

**Service Configuration:**
```
Services to Deploy:
1. junjo-backend
   - Image: mdrideout/junjo-ai-studio-backend:0.81.3
   - Port: 26154
   - Volume: /app/.dbdata

2. junjo-ingestion
   - Image: mdrideout/junjo-ai-studio-ingestion:0.81.3
   - Port: 26155
   - Volume: /app/.dbdata

3. junjo-frontend
   - Image: mdrideout/junjo-ai-studio-frontend:0.81.3
   - Port: 26153
```

**Internal Networking:**
- Railway provides internal DNS automatically
- Backend → Ingestion: private RPC at `junjo-ingestion.railway.internal:50052`
- Frontend → Backend: `http://junjo-backend.railway.internal:26154`
- Use Railway's service name for internal communication

**Environment Variables:**
Set in Railway dashboard for each service:
```bash
JUNJO_ENV=production
JUNJO_PROD_FRONTEND_URL=https://app.your-app.up.railway.app
JUNJO_PROD_BACKEND_URL=https://api.your-app.up.railway.app
JUNJO_PROD_INGESTION_URL=https://ingestion.your-app.up.railway.app
JUNJO_SESSION_SECRET=<generated-secret>
JUNJO_SECURE_COOKIE_KEY=<generated-secret>
JUNJO_ALLOW_ORIGINS=https://app.your-app.up.railway.app
```

**Public Access:**
- Railway provides automatic HTTPS
- Default: `*.up.railway.app` or `*.railway.app`
- Custom domains supported
- Generate domain in Railway dashboard

**Volume Management:**
- Volumes persist across deployments
- Backup: Use Railway CLI or manual exports
- Size limits depend on plan

**Cost Optimization:**
- Railway bills by usage (CPU/RAM/Network)
- Three services running simultaneously
- Consider sleep/wake cycles for dev environments

**Resources:**
- [Railway Docker Deployments](https://docs.railway.app/deploy/deployments)
- [Railway Volumes](https://docs.railway.app/reference/volumes)

---

## Reverse Proxy Configuration

**Note:** A reverse proxy is **optional** and only required for [Scenario 2](#scenario-2-external-access-reverse-proxy-required) (external access).

If you're using Scenario 2, you'll need to configure a reverse proxy to route traffic to the three services.

**Required routing:**
- Root domain → Frontend (port 26153)
- `api.` subdomain → Backend (port 26154)
- `ingestion.` subdomain → Ingestion (port 26155)

**Example routing table:**

| Service   | Compose Service & Internal Port          | Example Production URL         |
|-----------|----------------------------------------|--------------------------------|
| Frontend  | junjo-ai-studio-frontend:26153         | https://junjo.example.com           |
| Backend   | junjo-ai-studio-backend:26154          | https://api.junjo.example.com       |
| Ingestion | junjo-ai-studio-ingestion:26155        | https://ingestion.junjo.example.com |

See the `/examples` directory for reference configurations for popular reverse proxies:
- **Caddy Server** - `/examples/caddy/Caddyfile`

For a complete working example with Caddy bundled, see the [Junjo AI Studio Deployment Example](https://github.com/mdrideout/junjo-ai-studio-deployment-example).

## Junjo Application Telemetry Configuration

[Junjo's python library](https://python-api.junjo.ai/) uses OpenTelemetry to send structured AI graph workflow execution spans to Junjo AI Studio or any other OpenTelemetry destination.

The configuration differs based on your [deployment scenario](#deployment-scenarios). Choose the appropriate configuration below:

### Full Example

```python
import os

from junjo.telemetry.junjo_otel_exporter import JunjoOtelExporter
from opentelemetry import metrics, trace
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider


def setup_telemetry():
    """Set up OpenTelemetry providers for the application."""
    api_key = os.getenv("JUNJO_AI_STUDIO_API_KEY")
    if api_key is None:
        raise RuntimeError("JUNJO_AI_STUDIO_API_KEY is not set")

    resource = Resource.create({"service.name": "My Junjo Application"})

    # The Junjo AI Studio service name on the same Compose network
    junjo_exporter = JunjoOtelExporter(
        host="junjo-ai-studio-ingestion",  # Junjo AI Studio ingestion on the shared Docker network
        port="26155",
        api_key=api_key,
        insecure=True,
    )

    tracer_provider = TracerProvider(resource=resource)
    tracer_provider.add_span_processor(junjo_exporter.span_processor)
    trace.set_tracer_provider(tracer_provider)

    meter_provider = MeterProvider(
        resource=resource,
        metric_readers=[junjo_exporter.metric_reader],
    )
    metrics.set_meter_provider(meter_provider)

    return tracer_provider, meter_provider
```

Keep the returned providers for the application's lifetime, then call
`tracer_provider.shutdown()` and `meter_provider.shutdown()` during application shutdown.

For a complete end-to-end example, see the [Junjo AI Studio Deployment Example](https://github.com/mdrideout/junjo-ai-studio-deployment-example).

## Troubleshooting

### Session Cookie Issues
If you see "failed to get session" errors, clear your browser cookies for the domain and restart services.

### Port Conflicts
If ports 26153, 26154, or 26155 are already in use, find and stop the processes using those ports.

**Note:** Ports 50052 and 50053 are internal-only (not exposed to host) and used for service-to-service communication within the Docker network.

### Checking Logs
```bash
docker compose logs -f [service-name]
# Examples:
docker compose logs -f junjo-ai-studio-backend
docker compose logs -f junjo-ai-studio-ingestion
docker compose logs -f junjo-ai-studio-frontend
```

## License

This distribution is licensed under the Apache License 2.0. See
[`LICENSE`](LICENSE).

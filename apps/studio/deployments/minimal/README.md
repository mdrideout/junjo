# Junjo AI Studio - Minimal Build

> **Source and distribution:** The canonical source for this distribution is
> [`apps/studio/deployments/minimal`](https://github.com/mdrideout/junjo/tree/master/apps/studio/deployments/minimal)
> in the Junjo platform monorepo. The standalone
> [`junjo-ai-studio-minimal-build`](https://github.com/mdrideout/junjo-ai-studio-minimal-build)
> repository is the generated release mirror for convenient cloning. Submit
> changes to the canonical source; direct mirror changes are overwritten by
> the release publication workflow.

A minimal, opinionless Docker Compose setup for [Junjo AI Studio](https://github.com/mdrideout/junjo/tree/master/apps/studio) containing only the essential services. This minimal foundation provides the two core services needed to run Junjo AI Studio, with zero opinions about reverse proxies, networking, or infrastructure choices.

This template pins Junjo AI Studio `0.86.0`. Applications that emit Junjo workflow telemetry should use Junjo `0.69.0`.

> **Breaking upgrade policy:** Studio 0.85.0 (telemetry contract 3)
> requires wiping Studio application data and starting fresh with the matching
> SDK and Studio versions. Existing users, credentials, evaluations, and telemetry
> are not migrated. Follow the
> [canonical reset procedure](https://github.com/mdrideout/junjo/blob/master/apps/studio/deployments/RESET.md).
> `docker compose down --volumes` does not clear the host-mounted application data.
>
> Upgrading from Studio 0.85.0 or earlier to a later release needs the same
> reset and also changes the deployment: two containers instead of three, one
> Studio hostname, and six removed settings. Follow
> [Upgrading from Studio 0.85.0 or earlier](https://github.com/mdrideout/junjo/blob/master/apps/studio/deployments/RESET.md#upgrading-from-studio-0850-or-earlier).

A Junjo AI Studio instance can be used for an unlimited number of projects that use the [Junjo](https://github.com/mdrideout/junjo) python AI graph workflow framework. Any Junjo Application can send telemetry to this Junjo AI Studio instance, assuming it has valid API Key credentials.

> #### Full E2E Junjo Application Example:
>
>To see a full end-to-end opinionated deployment guide for a fresh Digital Ocean virtual machine, that includes a python application that uses the Junjo library to execute a graph workflow and sends telemetry to Junjo AI Studio, see this [Junjo AI Studio Deployment Example](https://github.com/mdrideout/junjo-ai-studio-deployment-example).

## What This Is

This is a **minimal build** template containing only the two essential Junjo AI Studio services:

**What's Included:**
- ✅ Two core services (app, ingestion)
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

Junjo AI Studio consists of two Docker services:

- **junjo-ai-studio-app**
  - **Web UI and HTTP API Port:** 26154
  - **Internal Port:** 50053 (gRPC for API key validation - Docker network only)
  - Web UI for viewing and debugging workflows
  - HTTP API server for authentication and data queries, on the same origin as the web UI
  - Uses SQLite for application data and metadata indexing
  - Queries cold Parquet telemetry and merges with ingestion hot snapshots
  - Served at the root domain (e.g., `https://junjo.example.com`)

- **junjo-ai-studio-ingestion**
  - **OTLP gRPC Port:** 26155
  - **Internal Port:** 50052 (gRPC for span reading - Docker network only)
  - High-throughput gRPC service for receiving OpenTelemetry traces
  - Uses Arrow IPC WAL segments and flushes to Parquet for durable cold storage
  - Provides internal gRPC for hot snapshot preparation
  - Your Python applications send trace telemetry to this service (e.g., `https://ingestion.junjo.example.com`)

**Security Note:** Internal ports (50052, 50053) are only accessible within the Docker network and are not exposed to the host machine. This ensures secure service-to-service communication.

### Data Flow

1. Python applications → **Ingestion Service** (OTLP gRPC on port 26155)
2. Ingestion Service → Arrow IPC WAL segments → flushes to Parquet
3. App → Calls ingestion internal gRPC (port 50052) for hot snapshots
4. App → Uses SQLite metadata index + Parquet files for trace queries
5. Web UI → Queries the app's HTTP API on the same origin → User views data

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
   - `production` asks for your Studio hostname and your ingestion hostname
   - It also applies a memory profile and generates the internal gRPC token
   - At completion, it prints the Studio and ingestion URLs and ports

   **Option B: Manual setup**
   ```bash
   cp .env.example .env
   ```
   Then generate and set the internal gRPC token:
   ```bash
   # Generate the token
   openssl rand -base64 32

   # Edit .env and replace:
   # - JUNJO_INTERNAL_GRPC_TOKEN with the generated value
   ```

3. Start services:
   ```bash
   docker compose up -d
   ```
   > Note: Docker Compose creates a project-scoped network automatically. Do not create or share a network manually.

4. Access Studio:
   - **Studio UI:** `http://localhost:26154`
     - _Troubleshooting: Try clearing your cookies if you encounter issues._
   - Create your first API key in the UI

5. Configure your Junjo Python application's exporter:
   ```python
   from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

   studio_exporter = OTLPSpanExporter(
       endpoint="localhost:26155",
       headers=(("x-junjo-api-key", JUNJO_AI_STUDIO_API_KEY),),
       insecure=True,
       timeout=120,
   )
   ```

**Note:** This repository always uses pre-built production Docker images from Docker Hub and does not use a `JUNJO_BUILD_TARGET` variable. For production runtime routing with a reverse proxy, set `JUNJO_ENV="production"` and `JUNJO_PROD_INGESTION_URL` (the setup script can do this automatically).

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
- Studio: `http://localhost:26154` (or the VM's IP address)
- Your application connects directly to `junjo-ai-studio-ingestion:26155` on the Docker network

**Python Configuration:**
```python
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

studio_exporter = OTLPSpanExporter(
    endpoint="junjo-ai-studio-ingestion:26155",
    headers=(("x-junjo-api-key", JUNJO_AI_STUDIO_API_KEY),),
    insecure=True,
    timeout=120,
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
- Studio (web UI and HTTP API): `https://junjo.example.com`
- Ingestion gRPC: `https://ingestion.junjo.example.com`

**Python Configuration:**
```python
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

studio_exporter = OTLPSpanExporter(
    endpoint="ingestion.junjo.example.com:443",
    headers=(("x-junjo-api-key", JUNJO_AI_STUDIO_API_KEY),),
    insecure=False,
    timeout=120,
)
```

### Scenario 3: Cloud Platform Deployments

**Use this when:**
- You want managed infrastructure without VM management
- Automatic SSL/TLS and domain routing
- Container orchestration handled for you
- Scalability and monitoring built-in

**Overview:**
Modern cloud platforms (Render, Railway) can host Junjo AI Studio's two services as separate containers with managed infrastructure. These platforms handle SSL/TLS, load balancing, and networking automatically.

**Key Considerations:**
- **Two separate services:** Each Junjo AI Studio service (app, ingestion) deploys independently
- **Persistent volumes:** Required for SQLite and spans storage (WAL/snapshots/Parquet)
- **Internal networking:** Services must communicate via internal URLs
- **Environment variables:** Configure `JUNJO_ENV="production"` along with `JUNJO_PROD_INGESTION_URL` and `JUNJO_INTERNAL_GRPC_TOKEN`
- **Cost:** Running 2 services simultaneously (check platform pricing)

---

#### Render

**Best For:** Teams wanting a Heroku-like experience with more flexibility

**Deployment Approach:**
- Create 2 separate "Web Services" from the Docker images:
  - `mdrideout/junjo-ai-studio-app:0.86.0`
  - `mdrideout/junjo-ai-studio-ingestion:0.86.0`
- Add persistent disks for data volumes

**Volume Configuration:**
```
App Service:
├─ /app/.dbdata/sqlite (SQLite app + metadata databases)
└─ /app/.dbdata/spans (Parquet cold data + hot snapshot access)

Ingestion Service:
└─ /app/.dbdata/spans (WAL, hot snapshot, and Parquet output)
```

**Internal Networking:**
- Services communicate via Render's internal network
- The app connects to ingestion via the private `junjo-ai-studio-ingestion:50052` RPC
- Ingestion connects to the app via the private `junjo-ai-studio-app:50053` RPC

**Environment Setup:**
```bash
JUNJO_ENV=production
JUNJO_PROD_INGESTION_URL=https://ingestion.your-domain.com
JUNJO_INTERNAL_GRPC_TOKEN=<generated-secret>
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
- Deploy 2 services from Docker images
- Add volumes for persistence
- Railway handles networking automatically

**Service Configuration:**
```
Services to Deploy:
1. junjo-ai-studio-app
   - Image: mdrideout/junjo-ai-studio-app:0.86.0
   - Port: 26154
   - Volume: /app/.dbdata

2. junjo-ai-studio-ingestion
   - Image: mdrideout/junjo-ai-studio-ingestion:0.86.0
   - Port: 26155
   - Volume: /app/.dbdata
```

**Internal Networking:**
- Railway provides internal DNS automatically
- App → Ingestion: private RPC at `junjo-ai-studio-ingestion.railway.internal:50052`
- Ingestion → App: private RPC at `junjo-ai-studio-app.railway.internal:50053`
- Use Railway's service name for internal communication

**Environment Variables:**
Set in Railway dashboard for each service:
```bash
JUNJO_ENV=production
JUNJO_PROD_INGESTION_URL=https://ingestion.your-app.up.railway.app
JUNJO_INTERNAL_GRPC_TOKEN=<generated-secret>
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
- Two services running simultaneously
- Consider sleep/wake cycles for dev environments

**Resources:**
- [Railway Docker Deployments](https://docs.railway.app/deploy/deployments)
- [Railway Volumes](https://docs.railway.app/reference/volumes)

---

## Reverse Proxy Configuration

**Note:** A reverse proxy is **optional** and only required for [Scenario 2](#scenario-2-external-access-reverse-proxy-required) (external access).

If you're using Scenario 2, you'll need to configure a reverse proxy to route traffic to the two services.

**Required routing:**
- Root domain → App (port 26154): the web UI and the HTTP API are one origin
- `ingestion.` subdomain → Ingestion (port 26155)

Route the whole Studio hostname to the app. If you add path rules, the API prefix is `/api/` with the trailing slash: `/api-keys` is a web UI page.

**Example routing table:**

| Service   | Compose Service & Internal Port          | Example Production URL         |
|-----------|----------------------------------------|--------------------------------|
| App       | junjo-ai-studio-app:26154              | https://junjo.example.com           |
| Ingestion | junjo-ai-studio-ingestion:26155        | https://ingestion.junjo.example.com |

See the `/examples` directory for reference configurations for popular reverse proxies:
- **Caddy Server** - `/examples/caddy/Caddyfile`

For a complete working example with Caddy bundled, see the [Junjo AI Studio Deployment Example](https://github.com/mdrideout/junjo-ai-studio-deployment-example).

## Junjo Application Telemetry Configuration

[Junjo's Python library](https://junjo.ai/docs/python/) uses OpenTelemetry to send structured AI graph workflow execution spans to Junjo AI Studio or any other OpenTelemetry destination.

Junjo AI Studio currently accepts OTLP traces only. The configuration below
creates no metric reader or periodic metric-export worker. An application can
configure an independent metrics pipeline for another OpenTelemetry destination.

The configuration differs based on your [deployment scenario](#deployment-scenarios). Choose the appropriate configuration below:

### Full Example

```python
import os

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor


def setup_telemetry():
    """Set up OpenTelemetry trace export for the application."""
    api_key = os.getenv("JUNJO_AI_STUDIO_API_KEY")
    if api_key is None:
        raise RuntimeError("JUNJO_AI_STUDIO_API_KEY is not set")

    resource = Resource.create({"service.name": "My Junjo Application"})

    # The Junjo AI Studio service name on the same Compose network
    studio_exporter = OTLPSpanExporter(
        endpoint="junjo-ai-studio-ingestion:26155",
        headers=(("x-junjo-api-key", api_key),),
        insecure=True,
        timeout=120,
    )

    tracer_provider = TracerProvider(resource=resource)
    tracer_provider.add_span_processor(BatchSpanProcessor(studio_exporter))
    trace.set_tracer_provider(tracer_provider)

    return tracer_provider
```

Keep the returned tracer provider for the application's lifetime, then call
`tracer_provider.shutdown()` during application shutdown.

For a complete end-to-end example, see the [Junjo AI Studio Deployment Example](https://github.com/mdrideout/junjo-ai-studio-deployment-example).

## Troubleshooting

### Session Cookie Issues
If you see "failed to get session" errors, clear your browser cookies for the domain and restart services.

### Port Conflicts
If ports 26154 or 26155 are already in use, find and stop the processes using those ports.

**Note:** Ports 50052 and 50053 are internal-only (not exposed to host) and used for service-to-service communication within the Docker network.

### Checking Logs
```bash
docker compose logs -f [service-name]
# Examples:
docker compose logs -f junjo-ai-studio-app
docker compose logs -f junjo-ai-studio-ingestion
```

## License

This distribution is licensed under the Apache License 2.0. See
[`LICENSE`](LICENSE).

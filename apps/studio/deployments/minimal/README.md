# Junjo Server - Bare Bones

A bare bones, opinionless Docker Compose setup for [Junjo Server](https://github.com/mdrideout/junjo-server) containing only the essential services. This minimal foundation provides the three core services needed to run Junjo Server, with zero opinions about reverse proxies, networking, or infrastructure choices.

A Junjo Server instance can be used for an unlimited number of projects that use the [Junjo](https://github.com/mdrideout/junjo) python AI graph workflow framework. Any Junjo Application can send telemetry to this Junjo Server, assuming it has valid API Key credentials.

> #### Full E2E Junjo Application Example:
>
>To see a full end-to-end opinionated deployment guide for a fresh Digital Ocean virtual machine, that includes a python application that uses the Junjo library to execute a graph workflow and sends telemetry to Junjo Server, see this [Junjo Server Deployment Example](https://github.com/mdrideout/junjo-server-deployment-example).

## What This Is

This is a **bare bones** template containing only the three essential Junjo Server services:

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
- Understanding Junjo Server architecture
- Local development environments
- Integration into existing infrastructure
- Incorporating into an existing docker-compose.yml

**Use the [Junjo Server Deployment Example](https://github.com/mdrideout/junjo-server-deployment-example) if you want:**
- Complete production-ready setup
- Bundled reverse proxy (Caddy)
- Demo application included
- Opinionated best practices

## Table of Contents

- [Junjo Server - Bare Bones](#junjo-server---bare-bones)
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
		- [Volume Permissions](#volume-permissions)
		- [Checking Logs](#checking-logs)

## Architecture

Junjo Server consists of three Docker services:

- **junjo-server-frontend** (Port 80)
  - Web UI for viewing and debugging workflows
  - Served at the root domain (e.g., `https://junjo.example.com`)

- **junjo-server-backend** (Port 1323, Internal Port 50053)
  - HTTP API server for authentication and data queries
  - Uses SQLite for application data and DuckDB for telemetry analytics
  - Polls ingestion service to process incoming telemetry
  - Served at the API subdomain (e.g., `https://api.junjo.example.com`)

- **junjo-server-ingestion** (Port 50051, Internal Port 50052)
  - High-throughput gRPC service for receiving OpenTelemetry data
  - Uses BadgerDB as a Write-Ahead Log (WAL) for durability
  - Backend service polls this service's internal API to batch-process spans
  - Your Python applications send telemetry to this service (e.g., `https://grpc.junjo.example.com`)

### Data Flow

1. Python applications → **Ingestion Service** (gRPC on port 50051)
2. Ingestion Service → BadgerDB WAL
3. Backend → Polls ingestion service (internal gRPC port 50052)
4. Backend → Indexes spans into DuckDB
5. Frontend → Queries backend API → User views data

## Quick Start

**Local Development Setup** (runs on localhost, no reverse proxy needed):

1. Clone this repository:
   ```bash
   git clone https://github.com/mdrideout/junjo-server-bare-bones.git
   cd junjo-server-bare-bones
   ```

2. Configure environment:
   ```bash
   cp .env.example .env
   ```

3. Generate and set your session secret:
   ```bash
   # Generate a secure key
   openssl rand -base64 48

   # Edit .env and replace JUNJO_SESSION_SECRET with the generated value
   ```

4. Start services:
   ```bash
   docker compose up -d
   ```

5. Access the frontend:
   - **Frontend UI:** `http://localhost:5153`
   - Create your first API key in the UI

6. Configure your Python application (same VM/Docker network):
   ```python
   junjo_server_exporter = JunjoServerOtelExporter(
       host="junjo-server-ingestion",  # Docker service name
       port="50051",
       api_key=JUNJO_SERVER_API_KEY,
       insecure=True,
   )
   ```

**Note:** The default `.env.example` is configured for local development (`JUNJO_ENV="development"`). For production deployment with a reverse proxy, see [Scenario 2](#scenario-2-external-access-reverse-proxy-required) and change `JUNJO_ENV="production"`.

For a complete working example with reverse proxy included, see the [Junjo Server Deployment Example](https://github.com/mdrideout/junjo-server-deployment-example).

## Deployment Scenarios

Choose the deployment scenario that matches your infrastructure:

### Scenario 1: Same VM/Network (No Reverse Proxy)

**Use this when:**
- Your Junjo application and Junjo Server run on the same virtual machine
- Services share a Docker network or VPC
- You don't need external services to send telemetry to Junjo Server

**Benefits:**
- Simpler setup - no reverse proxy configuration needed
- Direct container-to-container communication
- Lower latency
- No SSL/TLS overhead

**Access:**
- Frontend: `http://localhost:5153` (or VM's IP address)
- Your application connects directly to `junjo-server-ingestion:50051` on the Docker network

**Python Configuration:**
```python
junjo_server_exporter = JunjoServerOtelExporter(
    host="junjo-server-ingestion",  # Docker service name
    port="50051",                    # gRPC port
    api_key=JUNJO_SERVER_API_KEY,
    insecure=True,                   # No TLS needed on internal network
)
```

### Scenario 2: External Access (Reverse Proxy Required)

**Use this when:**
- Your Junjo application runs on a different server/cloud than Junjo Server
- You need multiple external services to send telemetry to Junjo Server
- You want HTTPS/TLS for secure communication

**Benefits:**
- Centralized Junjo Server for multiple applications
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
- Ingestion gRPC: `https://grpc.junjo.example.com`

**Python Configuration:**
```python
junjo_server_exporter = JunjoServerOtelExporter(
    host="grpc.junjo.example.com",   # Your domain
    port="443",                       # HTTPS port
    api_key=JUNJO_SERVER_API_KEY,
    insecure=False,                   # TLS enabled
)
```

### Scenario 3: Cloud Platform Deployments

**Use this when:**
- You want managed infrastructure without VM management
- Automatic SSL/TLS and domain routing
- Container orchestration handled for you
- Scalability and monitoring built-in

**Overview:**
Modern cloud platforms (Render, Railway) can host Junjo Server's three services as separate containers with managed infrastructure. These platforms handle SSL/TLS, load balancing, and networking automatically.

**Key Considerations:**
- **Three separate services:** Each Junjo service (backend, ingestion, frontend) deploys independently
- **Persistent volumes:** Required for SQLite, DuckDB, and BadgerDB data
- **Internal networking:** Services must communicate via internal URLs
- **Environment variables:** Configure `JUNJO_ENV="production"` and `JUNJO_PROD_AUTH_DOMAIN`
- **Cost:** Running 3 services simultaneously (check platform pricing)

---

#### Render

**Best For:** Teams wanting a Heroku-like experience with more flexibility

**Deployment Approach:**
- Create 3 separate "Web Services" from the Docker images:
  - `mdrideout/junjo-server-backend:latest`
  - `mdrideout/junjo-server-ingestion-service:latest`
  - `mdrideout/junjo-server-frontend:latest`
- Add persistent disks for data volumes

**Volume Configuration:**
```
Backend Service:
├─ /dbdata/sqlite (SQLite database)
└─ /dbdata/duckdb (DuckDB analytics)

Ingestion Service:
└─ /dbdata/badgerdb (BadgerDB WAL)
```

**Internal Networking:**
- Services communicate via Render's internal network
- Backend connects to ingestion via: `http://junjo-server-ingestion:50052`
- Frontend connects to backend via: `http://junjo-server-backend:1323`

**Environment Setup:**
```bash
JUNJO_ENV=production
JUNJO_PROD_AUTH_DOMAIN=yourapp.onrender.com
JUNJO_SESSION_SECRET=<generated-secret>
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
   - Image: mdrideout/junjo-server-backend:latest
   - Port: 1323
   - Volume: /dbdata/sqlite, /dbdata/duckdb

2. junjo-ingestion
   - Image: mdrideout/junjo-server-ingestion-service:latest
   - Port: 50051
   - Volume: /dbdata/badgerdb

3. junjo-frontend
   - Image: mdrideout/junjo-server-frontend:latest
   - Port: 80
```

**Internal Networking:**
- Railway provides internal DNS automatically
- Backend → Ingestion: `http://junjo-ingestion.railway.internal:50052`
- Frontend → Backend: `http://junjo-backend.railway.internal:1323`
- Use Railway's service name for internal communication

**Environment Variables:**
Set in Railway dashboard for each service:
```bash
JUNJO_ENV=production
JUNJO_PROD_AUTH_DOMAIN=your-app.up.railway.app
JUNJO_SESSION_SECRET=<generated-secret>
JUNJO_ALLOW_ORIGINS=https://your-app.up.railway.app
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
- Root domain → Frontend (port 80)
- `api.` subdomain → Backend (port 1323)
- `grpc.` subdomain → Ingestion (port 50051)

**Example routing table:**

| Service   | Docker Container & Internal Port     | Example Production URL         |
|-----------|--------------------------------------|--------------------------------|
| Frontend  | junjo-server-frontend:80             | https://junjo.example.com      |
| Backend   | junjo-server-backend:1323            | https://api.junjo.example.com  |
| Ingestion | junjo-server-ingestion:50051         | https://grpc.junjo.example.com |

See the `/examples` directory for reference configurations for popular reverse proxies:
- **Caddy Server** - `/examples/caddy/Caddyfile`

For a complete working example with Caddy bundled, see the [Junjo Server Deployment Example](https://github.com/mdrideout/junjo-server-deployment-example).

## Junjo Application Telemetry Configuration

[Junjo's python library](https://python-api.junjo.ai/) uses OpenTelemetry to send structured AI graph workflow execution spans to Junjo Server or any other OpenTelemetry destination.

The configuration differs based on your [deployment scenario](#deployment-scenarios). Choose the appropriate configuration below:

### Full Example

```python
import os

from junjo.telemetry.junjo_server_otel_exporter import JunjoServerOtelExporter

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider

def setup_telemetry():
	"""
	Sets up the OpenTelemetry tracer and exporter.
	"""

	# Load the JUNJO_SERVER_API_KEY from the environment variable
	JUNJO_SERVER_API_KEY = os.getenv("JUNJO_SERVER_API_KEY")
	if JUNJO_SERVER_API_KEY is None:
		print(
			"JUNJO_SERVER_API_KEY environment variable is not set. "
			"Generate a new API key in the Junjo Server UI."
		)
		return

	# Configure OpenTelemetry for this application
	resource = Resource.create({"service.name": "My Junjo Application"})
	tracer_provider = TracerProvider(resource=resource)

	# ============================================================================
	# Choose your deployment scenario:
	# ============================================================================

	# SCENARIO 1: Same VM/Network (No Reverse Proxy)
	# Use this when your app and Junjo Server share a Docker network or VPC
	junjo_server_exporter = JunjoServerOtelExporter(
		host="junjo-server-ingestion",  # Docker service name
		port="50051",                    # Direct gRPC port
		api_key=JUNJO_SERVER_API_KEY,
		insecure=True,                   # No TLS on internal network
	)

	# SCENARIO 2: External Access (Reverse Proxy)
	# Use this when your app is on a different server/network
	# junjo_server_exporter = JunjoServerOtelExporter(
	# 	host="grpc.junjo.example.com",   # Your public domain
	# 	port="443",                       # HTTPS port
	# 	api_key=JUNJO_SERVER_API_KEY,
	# 	insecure=False,                   # TLS enabled
	# )

	# Add the Junjo span processor
	tracer_provider.add_span_processor(junjo_server_exporter.span_processor)
	trace.set_tracer_provider(tracer_provider)

	return
```

For a complete end-to-end example, see the [Junjo Server Deployment Example](https://github.com/mdrideout/junjo-server-deployment-example).

## Troubleshooting

### Session Cookie Issues
If you see "failed to get session" errors, clear your browser cookies for the domain and restart services.

### Port Conflicts
If ports 1323, 50051, 50052, 50053, or 5153 are already in use, find and kill the processes using those ports. Improved port configuration among the services is planned.

### Volume Permissions
The backend requires root permissions to write to DuckDB volumes. If you encounter permission issues, ensure the user is set to `root` in the backend service configuration.

### Checking Logs
```bash
docker compose logs -f [service-name]
# Examples:
docker compose logs -f junjo-server-backend
docker compose logs -f junjo-server-ingestion
docker compose logs -f junjo-server-frontend
```
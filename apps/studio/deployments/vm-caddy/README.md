# Junjo Server - Production VM Deployment Example

This repository walks you through creating a complete production deployment of Junjo Server that you can run on a cheap VM, allowing your AI applications to send telemetry data for debugging, observability, and workflow analysis.

**Bare Bones Github Template:** For a bare-bones Junjo Server template with no pre-configuration or opinions about deployment environments, check out the [Junjo Server Bare Bones Template](https://github.com/mdrideout/junjo-server-bare-bones)

## Table of Contents

- [Prerequisites](#prerequisites)
- [Quick Start (Local Development)](#quick-start-local-development)
- [Production VM Deployment](#production-vm-deployment)
  - [1. Creating a VM (Digital Ocean Example)](#1-creating-a-vm-digital-ocean-example)
  - [2. DNS Configuration & Service Endpoints](#2-dns-configuration--service-endpoints)
  - [3. Server Configuration](#3-server-configuration)
  - [4. Block Storage (Optional)](#4-block-storage-optional)
  - [5. Services Architecture](#5-services-architecture)
- [Miscellaneous](#miscellaneous)
  - [SSL Testing with Let's Encrypt Staging](#ssl-testing-with-lets-encrypt-staging)

## Overview

Deploy Junjo Server as a centralized observability backend for your AI applications. Once deployed, your Python applications can send OpenTelemetry data to Junjo Server using the `JunjoServerOtelExporter`, giving you:

- **Complete workflow visibility**: See every step your LLM takes in a sequence of events
- **Decision transparency**: Understand what data your AI is using to make decisions
- **Debugging interface**: Web UI for exploring and analyzing workflow executions
- **Production-ready**: Includes reverse proxy with automatic SSL, session management, and scalable ingestion

This deployment includes a demo Python application (`junjo-app`) that shows you exactly how to integrate Junjo Server into your own projects.

## What's Included

This deployment provides everything you need to run Junjo Server in production:

### Core Services
- **Junjo Server Backend**: HTTP API, authentication, and business logic (SQLite + DuckDB)
- **Junjo Server Ingestion**: High-throughput OpenTelemetry gRPC endpoint (BadgerDB WAL)
- **Junjo Server Frontend**: Web-based debugging and workflow visualization interface

### Infrastructure
- **Caddy Reverse Proxy**: Automatic HTTPS with Let's Encrypt, subdomain routing
- **Docker Compose**: Complete orchestration with health checks and dependency management
- **Example Python App**: Reference implementation showing how to connect your AI applications

### Production Features
- Session-based authentication with cookie management
- Automatic SSL certificate generation and renewal
- Cloudflare DNS integration for wildcard domains
- Persistent data storage with volume management
- Scalable architecture with decoupled ingestion

## Prerequisites

*   [Docker](https://docs.docker.com/get-docker/)
*   [Docker Compose](https://docs.docker.com/compose/install/)

## Quick Start (Local Development)

Test the deployment locally before deploying to production. The following steps will run Junjo Server on your local machine with the demo application.

### 1. Clone this Repository

```bash
git clone https://github.com/mdrideout/junjo-server-deployment-example.git
cd junjo-server-deployment-example
```

### 2. Configure Environment Variables

Copy the example environment file and update it with your own secret key.

```bash
cp .env.example .env
```

Update the `JUNJO_SESSION_SECRET` environment variable. Open `.env` in your editor and replace `your_secret_key` with a new key. You can generate one with the following command:

```bash
openssl rand -base64 48
```

### 3. Run the Application

The `caddy/Caddyfile` is configured for local development by default (no SSL required). Start all the services using Docker Compose:

```bash
docker compose up --build
```

### 4. Access the Services

Once all the services are running, you can access them in your browser:

*   **Junjo Server UI**: [http://localhost:5153](http://localhost:5153)

The **demo application (`junjo-app`) automatically starts running a workflow every 5 seconds**, continuously sending telemetry to Junjo Server. You'll see new workflow runs appearing in real-time!

Watch the demo app in action:
```bash
# View demo app logs
docker logs -f junjo-app

# You'll see output like:
# Executing workflow...
# Workflow started.
# Counter incremented to: 1
# Workflow finished.
```

#### App API Key Setup Steps:

1.  Navigate to [http://localhost:5153](http://localhost:5153) and create your user account, then sign in.
2.  Create an [API key](http://localhost:5153/api-keys) in the Junjo Server UI.
3.  Set this key as the `JUNJO_SERVER_API_KEY` environment variable in your `.env` file.
4.  Recreate the `junjo-app` container to apply the new API key in the .env file:
    ```bash
    docker compose up --force-recreate --no-deps junjo-app -d
    ```

> **Troubleshooting:** If you see a "failed to get session" error in the logs or have trouble logging in, try clearing your browser's cookies for `localhost` and restarting the services. This can happen if you have multiple Junjo server projects running on `localhost` and an old session cookie is interfering.

**What You'll See:**
- New workflow runs appearing every 5 seconds in the UI
- Each run shows the complete execution trace (3 nodes: Start → Increment → End)
- Click any run to explore the workflow execution details, timing, and state changes
- This demonstrates real-time telemetry ingestion and visualization

### 5. Stopping the Application

To stop all the services, press `Ctrl+C` in the terminal where `docker compose` is running. To remove the containers and their volumes, run:

```bash
docker compose down -v
```

---

# Production VM Deployment

Deploy Junjo Server to a cloud VM to provide a centralized observability backend for your AI applications running anywhere. Your applications will connect to your deployed Junjo Server instance via the gRPC ingestion endpoint.

### 1. Creating a VM (Digital Ocean Example)

Create a Droplet with the following specifications *($6/mo)*:

- **OS**: Debian 13
- **RAM**: 1GB
- **vCPU**: 1
- **Disk**: 25GB SSD

This single VM can ingest telemetry from an unlimited number of AI applications running anywhere.

#### 1a. Add a static IP address

This will allow us to point a domain to this VM and complete the following SSL setup.

### 2. DNS Configuration & Service Endpoints

#### Domain Setup

The `JUNJO_PROD_AUTH_DOMAIN` environment variable defines your primary production domain and controls:

1. **Frontend Access**: The web UI domain for viewing workflows
2. **Session Cookies**: Domain-wide authentication (covers all subdomains)
3. **API & gRPC Endpoints**: Subdomain routing for backend services

**Requirements:**
- A wildcard DNS record for your domain (e.g., `*.example.com`)
- Cloudflare API token for automatic SSL (or configure alternative DNS provider)

#### DNS Configuration

Configure your DNS provider with A records pointing to your server's IP address. The following A records assume the following environment variable: `JUNJO_PROD_AUTH_DOMAIN=junjo.example.com`

| Record Type | Hostname | Value | TTL |
|-------------|----------|-------|-----|
| A | `*.junjo.example.com` | `your-server-ip` | 300 |
| A | `junjo.example.com` | `your-server-ip` | 300 |

> Replace `junjo.example.com` with your actual domain and `your-server-ip` with your VM's public IP address. The wildcard record (`*`) ensures all subdomains (api, grpc) route to your server.

#### Service Endpoints

Assuming `JUNJO_PROD_AUTH_DOMAIN=junjo.example.com`, your deployment will be accessible at:

| Service | URL | Purpose |
|---------|-----|---------|
| **Web UI** | `https://junjo.example.com` | View and debug AI workflow executions |
| **API** | `https://api.junjo.example.com` | Backend HTTP API |
| **Ingestion** | `grpc.junjo.example.com:443` | **Your AI applications send telemetry here** |

#### CORS Settings

Update the allowed origins in the `.env` file to include your production domain:

```yaml
JUNJO_ALLOW_ORIGINS=http://junjo.example.com,https://junjo.example.com
```

#### Connecting Your AI Applications

Configure your Python applications to send OpenTelemetry data to the ingestion endpoint:

```python
from junjo.telemetry.junjo_server_otel_exporter import JunjoServerOtelExporter

junjo_exporter = JunjoServerOtelExporter(
    host="grpc.junjo.example.com",  # Your production domain
    port="443",                       # HTTPS port (Caddy handles SSL)
    api_key="your_api_key",          # Created in Junjo Server UI
    insecure=False,                   # Use SSL in production
)
```

See the `junjo_app/` directory for a complete working example.

### 3. Server Configuration

#### SSH into the Server

```bash
ssh root@[your-ip-address]
```

#### Install Docker & Docker Compose

1. Follow [Install Docker Engine on Debian](https://docs.docker.com/engine/install/debian/) instructions
2. Install rsync: `sudo apt install rsync`
3. Disconnect from SSH for the next steps

#### Copy Files & Launch

From your local machine, copy the repository files to the server:

```bash
# Copy via rsync (run from your local machine)
# Exclude hidden files except for .env.example
rsync -avz --delete -e ssh --include='.env.example' --exclude='.??*' ~/project/root/path/on/local/machine root@[your-ip-address]:

# SSH back into the server
ssh root@[your-ip-address]

# Navigate to the deployment directory (should be the same folder name as the repository root)
cd ~/junjo-server-deployment-example

# Verify files were copied correctly
ls -a

# Generate a session secret key and keep it for JUNJO_SESSION_SECRET variable
openssl rand -base64 48

# Copy the example environment variable file to a new .env
cp .env.example .env

# Edit the .env to add variables for production, including
# JUNJO_ENV="production", JUNJO_PROD_AUTH_DOMAIN, JUNJO_SESSION_SECRET, CF_API_TOKEN
vi .env

# Configure Caddy for production
# Edit caddy/Caddyfile: comment out the local development section
# and uncomment the production section. See the Caddyfile for detailed instructions.
vi caddy/Caddyfile

# The JUNJO_SERVER_API_KEY variable will be set later after we create an API key in the Junjo Server UI.
```

#### Start The Services

```bash
# Pull latest images and start services - thie xcaddy build may take a few minutes
docker compose pull && docker compose up -d --build

# Monitor startup logs
docker logs -f junjo-caddy  # Check for successful SSL certificate generation

# You should find a message in the logs that contains ..."msg":"authorization finalized"...
```

#### Create API Key

1. Access the frontend at `https://junjo.example.com` (same as your `JUNJO_PROD_AUTH_DOMAIN`)
2. Create a user account and sign in
3. Navigate to API Keys and create a new key
4. Update `.env` with your API key:
   ```bash
   vi .env  # Set JUNJO_SERVER_API_KEY
   ```
5. Restart the demo app to apply the key:
   ```bash
   docker compose restart junjo-app
   ```

#### Verify Deployment

```bash
# Check all containers are running
docker container ls

# Watch application logs
docker logs -f junjo-app
```

Your Junjo Server is now live! Visit the Web UI to see workflow runs from the demo application.

### 4. Block Storage (Optional)

**Recommended for production deployments.** Block storage separates your persistent data from the VM instance, providing better durability and backup capabilities. Benefits include:

- **Independence**: Data survives VM rebuilds or migrations
- **Scalability**: Resize storage independently of compute resources
- **Better backups**: Use cloud provider snapshot features
- **Portability**: Detach and reattach volumes to different VMs

Most cloud providers (Digital Ocean, AWS, GCP, Azure, Hetzner) offer block storage through their dashboards. Create a volume, attach it to your VM, mount it to `/mnt/junjo-data`, then update the volume paths in `docker-compose.yml` to point to `/mnt/junjo-data/sqlite`, `/mnt/junjo-data/duckdb`, and `/mnt/junjo-data/badgerdb`.

### 5. Services Architecture

This deployment includes several interconnected services. The **core Junjo Server services** provide the observability platform, while **infrastructure services** handle routing and SSL.

### Core Junjo Server Services

#### `junjo-server-ingestion`
*   **Image**: `mdrideout/junjo-server-ingestion-service:latest`
*   **Purpose**: High-throughput OpenTelemetry data ingestion
*   **Details**: Lightweight Go service that receives telemetry via gRPC (port 50051) and writes to BadgerDB as a Write-Ahead Log. This decoupled architecture ensures data isn't lost during backend maintenance or restarts.

#### `junjo-server-backend`
*   **Image**: `mdrideout/junjo-server-backend:latest`
*   **Purpose**: API server, authentication, and data processing
*   **Details**: Go-based Echo application that handles HTTP API requests (port 1323), user authentication, and business logic. Polls the ingestion service's WAL to index telemetry into DuckDB for fast querying. Uses SQLite for user/session data.

#### `junjo-server-frontend`
*   **Image**: `mdrideout/junjo-server-frontend:latest`
*   **Purpose**: Web-based debugging interface
*   **Details**: React application providing the UI for viewing workflow runs, exploring traces, and analyzing AI agent behavior. Served on port 80 (internally), proxied through Caddy.

### Infrastructure Services

#### `caddy`
*   **Source**: [`caddy/`](caddy/)
*   **Purpose**: Reverse proxy with automatic HTTPS
*   **Details**: Routes traffic to appropriate services, handles SSL certificate generation/renewal via Let's Encrypt, and provides subdomain-based routing. See [`caddy/Caddyfile`](caddy/Caddyfile) for configuration.

### Demo Application (Reference Implementation)

#### `junjo-app`
*   **Source**: [`junjo_app/`](junjo_app/)
*   **Purpose**: Example showing how to integrate Junjo Server into your Python applications
*   **Details**: Runs a simple 3-node Junjo workflow (StartNode → IncrementNode → EndNode) in a continuous loop, executing **every 5 seconds**. Each execution generates a complete OpenTelemetry trace showing state changes, node timing, and workflow decision flow. This continuous telemetry stream demonstrates real-time ingestion and visualization.

**What the Demo Does:**
- Executes a workflow that increments a counter
- Sends complete trace data to `junjo-server-ingestion` via gRPC
- Creates visible workflow runs in the Junjo Server UI every 5 seconds
- Shows how to configure `JunjoServerOtelExporter` in your own applications
- Watch it running: `docker logs -f junjo-app`

**For Production:**
Use `junjo_app/` as a reference implementation. **Remove this service** from `docker-compose.yml` if you don't need the demo running continuously.

---

# Miscellaneous

## SSL Testing with Let's Encrypt Staging

Let's Encrypt rate limits SSL certificate issuance. When setting up a new environment, use the Let's Encrypt staging environment to avoid production rate limits during testing.

To enable staging certificates, uncomment the following line in your `.env` file:

```yaml
# === FOR SSL TESTING ============================================================================>
# ...
JUNJO_LETS_ENCRYPT_STAGING_CA_DIRECTIVE="ca https://acme-staging-v02.api.letsencrypt.org/directory"
```

Caddy will automatically use the Let's Encrypt staging environment when generating certificates.

**Note:** Without manually trusting these staging certificates, you will see a "Your connection is not private" warning in your browser.

### Trusting Staging Certificates (macOS)

To test your setup without browser warnings, add the staging certificate to your macOS Keychain Access:

1. Download the staging certificates:
   ```bash
   bash download_staging_certs.sh
   ```

2. Open the `.certs` folder in Finder and double-click the `.pem` files to add them to Keychain Access

3. In Keychain Access, double-click each new certificate and expand the "Trust" section

4. Select "Always Trust" for both certificates

5. Restart your browser (Chrome or Safari)


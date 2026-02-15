# Junjo AI Studio - Production VM Deployment Example

This is a production deployment example of Junjo AI Studio, a Junjo python SDK powered app, and Caddy reverse proxy to a fresh virtual machine.

Learn how to go from a fresh virtual machine to a production deployment that supports an unlimited number of users and junjo apps. 

- ⚙️ Setup and configure a new Virtual Machine
- 🔀 Turn-key Caddy reverse proxy with SSL support
- 🎏 Example Junjo python SDK powered app (demonstrates real telemetry)
- 🚀 Junjo AI Studio in production

**See Also: Minimal Build Github Template:** For a minimal build repository template for Junjo AI Studio, without caddy, no example app, and no opinions about deployment environments, check out the [Junjo AI Studio - Minimal Build](https://github.com/mdrideout/junjo-ai-studio-minimal-build)

- Perfect for incorporating into an existing server or existing `docker-compose.yml` setup.

---

## Table of Contents

- [Prerequisites](#prerequisites)
- [Local Quick Start](#local-quick-start)
- [Production VM Deployment](#production-vm-deployment)
  - [1. Creating a VM (Digital Ocean Example)](#1-creating-a-vm-digital-ocean-example)
  - [2. DNS Configuration & Service Endpoints](#2-dns-configuration--service-endpoints)
  - [3. Server Configuration](#3-server-configuration)
  - [4. Block Storage (Optional)](#4-block-storage-optional)
  - [5. Services Architecture](#5-services-architecture)
- [Miscellaneous](#miscellaneous)
  - [SSL Testing with Let's Encrypt Staging](#ssl-testing-with-lets-encrypt-staging)

## Overview

Deploy Junjo AI Studio as a centralized observability backend for your AI applications. Once deployed, your Python applications can send OpenTelemetry data to Junjo AI Studio using the `JunjoOtelExporter`, giving you:

- **Complete workflow visibility**: See every step your LLM takes in a sequence of events
- **Decision transparency**: Understand what data your AI is using to make decisions
- **Debugging interface**: Web UI for exploring and debugging workflow executions and state changes
- **Production-ready**: Includes reverse proxy with automatic SSL, authentication and user management, and scalable ingestion

This deployment includes a demo Python application (`junjo-app`) that shows you exactly how to integrate Junjo AI Studio into your own projects.
The three Junjo AI Studio core services use pinned pre-built Docker images, while `caddy` and `junjo-app` are built from this repository.

### Core Services
- **Junjo AI Studio Backend**: HTTP API, authentication, and query orchestration (SQLite metadata + Parquet queries + hot snapshot merge)
- **Junjo AI Studio Ingestion**: High-throughput OpenTelemetry gRPC endpoint (Arrow IPC WAL + Parquet flush)
- **Junjo AI Studio Frontend**: Web-based debugging and workflow visualization interface

### Infrastructure
- **Caddy Reverse Proxy**: Automatic HTTPS with Let's Encrypt, subdomain routing
- **Docker Compose**: Complete orchestration with health checks and dependency management
- **Example Python App**: Reference implementation showing how to connect your AI applications

## Prerequisites

*   [Docker](https://docs.docker.com/get-docker/)
*   [Docker Compose](https://docs.docker.com/compose/install/)

## Local Quick Start

The following steps will run Junjo AI Studio on your local machine with the demo application.

### 1. Clone this Repository

```bash
git clone https://github.com/mdrideout/junjo-ai-studio-deployment-example.git
cd junjo-ai-studio-deployment-example
```

### 2. Configure Environment Variables

Choose a setup path:

#### **Option 1: Script setup**

   ```bash
   ./scripts/junjo setup
   ```

   The setup script can generate secrets, derive production URLs, and set `CLOUDFLARE_API_TOKEN` for production mode. It does not edit `caddy/Caddyfile`.

#### **Option 2: Manual setup**

   ```bash
   cp .env.example .env
   ```

Generate and set TWO required security keys:

Both `JUNJO_SESSION_SECRET` and `JUNJO_SECURE_COOKIE_KEY` must be set for the backend to function properly.

1. Generate the first key:
   ```bash
   openssl rand -base64 32
   ```

2. Open `.env` in your editor and replace `your_base64_secret_here` in `JUNJO_SESSION_SECRET` with the generated key

3. Generate the second key:
   ```bash
   openssl rand -base64 32
   ```

4. Replace `your_base64_key_here` in `JUNJO_SECURE_COOKIE_KEY` with this second generated key

For production deployments, also set these values in `.env`:
- `JUNJO_ENV=production`
- `JUNJO_PROD_FRONTEND_URL=https://junjo.example.com`
- `JUNJO_PROD_BACKEND_URL=https://api.junjo.example.com`
- `JUNJO_PROD_INGESTION_URL=https://ingestion.junjo.example.com`
- `CLOUDFLARE_API_TOKEN=<your_token>` (required for Caddy DNS challenge / automatic SSL for this deployment example.)

### 3. Run the Application

The `caddy/Caddyfile` is configured for local development by default (no SSL required). Start all the services using Docker Compose:

```bash
docker compose up --build
```

Docker Compose creates and labels `junjo_network` automatically for this stack. Do not manually pre-create this network.

### 4. Access the Services

Once all the services are running, you can access them in your browser:

*   **Junjo AI Studio UI**: [http://localhost:5153](http://localhost:5153)

#### 🚨 Demo App Requires Initial Setup

The **demo application (`junjo-app`) automatically starts**. When configured with an API key, it will continuously execute a simple workflow in a loop, sending telemetry to Junjo AI Studio. 

1. Create its API key
2. Set the `.env` variable
3. Restart the container
4. Observe workflow runs appearing inside Junjo AI Studio

#### 🔑 App API Key Setup Steps:

1.  Navigate to [http://localhost:5153](http://localhost:5153) and create your user account, then sign in.
2.  Create an [API key](http://localhost:5153/api-keys) in the Junjo AI Studio UI.
3.  Set this key as the `JUNJO_AI_STUDIO_API_KEY` environment variable in your `.env` file.
4.  Recreate the `junjo-app` container to apply the new API key in the .env file:
    ```bash
    docker compose up --force-recreate --no-deps junjo-app -d
    ```

> **Troubleshooting:** If you see a "failed to get session" error in the logs or have trouble logging in, try clearing your browser's cookies for `localhost` and restarting the services. This can happen if you have multiple Junjo AI Studio projects running on `localhost` and an old session cookie is interfering.

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

Deploy Junjo AI Studio to a cloud VM to provide a centralized observability backend for your AI applications running anywhere. Your applications will connect to your deployed Junjo AI Studio instance via the gRPC ingestion endpoint.

### 1. Creating a VM (Digital Ocean Example)

Create a Droplet with the following specifications *($6/mo)*:

- **OS**: Debian 13
- **RAM**: 1GB
- **vCPU**: 1
- **Disk**: 25GB SSD

For backend memory tuning defaults:
- 1GB VM: use `./scripts/junjo setup --profile 1g` (default)
- 2GB VM: use `./scripts/junjo setup --profile 2g`
- 4GB VM: use `./scripts/junjo setup --profile 4g`

This single VM can ingest telemetry from an unlimited number of AI applications running anywhere.

#### 1a. Add a static IP address

This will allow us to point a domain to this VM and complete the following SSL setup.

### 2. DNS Configuration & Service Endpoints

#### Domain Setup

Your production domain configuration is manually set in the `caddy/Caddyfile`. This gives you full control over:

1. **Frontend Access**: The web UI domain for viewing workflows
2. **Session Cookies**: Domain-wide authentication (covers all subdomains)
3. **API & Ingestion Endpoints**: Subdomain routing for backend services

**Requirements:**
- A registered domain with DNS access
- A records pointing to your server's IP
- Cloudflare API token for automatic SSL (or configure alternative DNS provider)
  - See cloudflare single API token setup here: https://github.com/caddy-dns/cloudflare

#### DNS Configuration

Configure your DNS provider with A records pointing to your server's IP address. This example uses `junjo.example.com`:

| Record Type | Hostname | Value | TTL |
|-------------|----------|-------|-----|
| A | `*.junjo.example.com` | `your-server-ip` | 300 |
| A | `junjo.example.com` | `your-server-ip` | 300 |

> Replace `junjo.example.com` with your actual subdomain and `your-server-ip` with your VM's public IP address. The wildcard record (`*`) ensures all sub-subdomains (api, ingestion) route to your server.

#### Service Endpoints

Using `junjo.example.com` as an example, your deployment will be accessible at:

| Service | URL | Purpose |
|---------|-----|---------|
| **Web UI** | `https://junjo.example.com` | View and debug AI workflow executions |
| **API** | `https://api.junjo.example.com` | Backend HTTP API |
| **Ingestion** | `ingestion.junjo.example.com:443` | **Your AI applications send telemetry here** |

#### Connecting Your AI Applications

Configure your Python applications to send OpenTelemetry data to the ingestion endpoint:

```python
from junjo.telemetry.junjo_server_otel_exporter import JunjoServerOtelExporter

junjo_exporter = JunjoServerOtelExporter(
    host="ingestion.junjo.example.com",  # Your production ingestion domain
    port="443",                            # HTTPS port (Caddy handles SSL)
    api_key="your_api_key",               # Created in Junjo AI Studio UI
    insecure=False,                        # Use SSL in production
)
```

See the `junjo_app/` directory for a complete working example.

### 3. Server Configuration

Your fresh debian server needs a few things to be installed to be able to run rsync and docker.

#### SSH into the Server

```bash
ssh root@[your-ip-address]
```

#### Install Docker & Docker Compose

1. Follow [Install Docker Engine on Debian](https://docs.docker.com/engine/install/debian/) instructions
2. Install rsync: `sudo apt install rsync`
3. Disconnect from SSH for the next steps: `exit`

#### Copy Files To Server

From your local machine, copy the repository files to the server:

- _Copies via rsync (run from your local machine), excludes hidden files except for .env.example_
- `/Users/user/...` path is the full path to your project folder on your machine
- Note the `:/projects` after the IP address
- Uplads to `<server_root>/projects`

```bash
# Run from the root of the project directory you want to transfer
rsync -avz --delete -e ssh --include='.env.example' --exclude='.??*' /Users/user/path/to/project-dir root@[your-ip-address]:/projects
```

### 4. Configure Files For Production

The following steps walk you through configuring environment variables and Caddy for production.

These changes can be made locally and rsync'd to the server, or you can make them on the server using the **vi** editor.
- _Note: the above rsync command excludes `.env`  would require changes to rsync the .env file_

#### SSH into the server again
```bash
# SSH into the server
ssh root@[your-ip-address]

# Change directory to the server root
cd /

# Find the projects folder
ls -a

# Navigate to projects
cd projects

# Verify all files are there
ls -a
```

#### Verify Your Project Folder Is There

This should show a folder for the repo you transferred via `rsync`.

```bash
# Verify files were copied correctly
ls -a

# Change directories into the project folder
cd <project-folder-name>
```

#### Environment Variable Setup

```bash
# Copy the example environment file
cp .env.example .env

# Generate TWO security keys (run twice and use different values)
openssl rand -base64 32  # JUNJO_SESSION_SECRET
openssl rand -base64 32  # JUNJO_SECURE_COOKIE_KEY

# Edit .env and set production values:
# - JUNJO_ENV=production
# - JUNJO_PROD_FRONTEND_URL=https://junjo.example.com
# - JUNJO_PROD_BACKEND_URL=https://api.junjo.example.com
# - JUNJO_PROD_INGESTION_URL=https://ingestion.junjo.example.com
# - JUNJO_SESSION_SECRET=<generated_key_1>
# - JUNJO_SECURE_COOKIE_KEY=<generated_key_2>
# - CLOUDFLARE_API_TOKEN=<required_for_caddy_dns_challenge>
vi .env
```

Optional convenience:

```bash
./scripts/junjo setup --env production --hostname junjo.example.com
# or
./scripts/junjo setup --non-interactive --env production --hostname junjo.example.com --cloudflare-token <your_token>
```

The setup script updates `.env` values only. It does not edit `caddy/Caddyfile`.

#### Caddyfile setup

Configures the Caddy reverse proxy container to handle traffic from your production domains / subdomains.
- _Note: google `vi multiline comment / uncomment` for shortcuts_

```bash
# 1. Comment out the local development section
# 2. Uncomment the production section
# 3. Replace 'junjo.your-domain.com' with your actual subdomain
# 4. Replace 'your-email@example.com' with your email
# See the Caddyfile for detailed instructions.
vi caddy/Caddyfile
```

#### Start The Services

- Pull configured images and start services
- Note: the first build of xcaddy image may take a few minutes, subsequent launches are faster.

```bash
docker compose pull && docker compose up -d --build
```

If you previously created `junjo_network` manually, remove it once before startup so Compose can recreate it with the correct labels:

```bash
docker network rm junjo_network
docker compose up -d
```

#### Validate SSL

Proper DNS setup, Caddy setup, and Cloudflare Token setup will result in the following logs being visible.

```bash
# Check caddy logs for successful SSL setup
docker logs -f junjo-caddy

# Search logs for "authorization finalized"
```

*Example:*

```bash
{"level":"info","ts":1763843812.5458374,"msg":"authorization finalized","identifier":"*.junjo.example.com","authz_status":"valid"}
{"level":"info","ts":1763843812.5465696,"msg":"validations succeeded; finalizing order"...
{"level":"info","ts":1763843812.9823546,"msg":"authorization finalized","identifier":"junjo.example.com","authz_status":"valid"}
{"level":"info","ts":1763843812.9825242,"msg":"validations succeeded; finalizing order"....
```

#### Create API Key

1. Access the frontend at your production domain (e.g., `https://junjo.example.com`)
2. Create a user account and sign in
3. Create the API Key
4. Update `.env` and set `JUNJO_AI_STUDIO_API_KEY` with your API key:
   ```bash
   vi .env
   ```
5. Restart the demo app to apply the key:
   ```bash
   docker compose up --force-recreate --no-deps junjo-app -d
   ```
6. View the logs of the sample junjo-app executing:
   ```bash
   docker logs -f junjo-app
   ```

#### Verify Deployment

```bash
# Check all containers are running
docker container ls

# Watch application logs
docker logs -f junjo-app
```

Your Junjo AI Studio is now live! Visit the Web UI to see workflow runs from the demo application.

### 4. Block Storage (Optional)

**Recommended for production deployments.** Block storage separates your persistent data from the VM instance, providing better durability and backup capabilities. Benefits include:

- **Independence**: Data survives VM rebuilds or migrations
- **Scalability**: Resize storage independently of compute resources
- **Better backups**: Use cloud provider snapshot features
- **Portability**: Detach and reattach volumes to different VMs

#### Setup Instructions

The docker-compose.yml is pre-configured to use the `JUNJO_HOST_DB_DATA_PATH` environment variable. You only need to configure this variable in your `.env` file.

**Steps:**

1. **Create and attach block storage volume** through your cloud provider's dashboard (Digital Ocean, AWS EBS, GCP Persistent Disk, Azure Disk, etc.)

2. **Mount the volume to your VM**. Example for common providers:
   ```bash
   # DigitalOcean Volume
   sudo mkdir -p /mnt/junjo-data
   sudo mount -o discard,defaults,noatime /dev/disk/by-id/scsi-0DO_Volume_* /mnt/junjo-data

   # AWS EBS
   sudo mkdir -p /mnt/junjo-data
   sudo mount /dev/xvdf /mnt/junjo-data

   # Google Cloud Persistent Disk
   sudo mkdir -p /mnt/junjo-data
   sudo mount /dev/disk/by-id/google-* /mnt/junjo-data
   ```

3. **Update your `.env` file** to point to the mounted volume:
   ```bash
   JUNJO_HOST_DB_DATA_PATH=/mnt/junjo-data
   ```

4. **Restart services** to apply the new configuration:
   ```bash
   docker compose down
   docker compose up -d
   ```

The databases will now be stored in:
- `/mnt/junjo-data/sqlite/` (SQLite - user/session data)
- `/mnt/junjo-data/spans/wal/` (Arrow IPC WAL segments - hot ingestion buffer)
- `/mnt/junjo-data/spans/parquet/` (Parquet files - cold span storage and analytics)
- `/mnt/junjo-data/spans/hot_snapshot.parquet` (hot snapshot parquet used for near-real-time queries)

### 5. Services Architecture

This deployment includes several interconnected services. The **core Junjo AI Studio services** provide the observability platform, while **infrastructure services** handle routing and SSL.

### Core Junjo AI Studio Services

#### `junjo-ai-studio-ingestion`
*   **Image**: `mdrideout/junjo-ai-studio-ingestion:0.81.0`
*   **Purpose**: High-throughput OpenTelemetry data ingestion
*   **Details**: Rust service that receives telemetry via gRPC (port 50051), writes spans to Arrow IPC WAL segments, and flushes spans to Parquet for durable cold storage. It also prepares a hot snapshot parquet file for low-latency recent queries.
*   **Health Check**: Docker health check verifies the internal gRPC port (`50052`) is listening.

#### `junjo-ai-studio-backend`
*   **Image**: `mdrideout/junjo-ai-studio-backend:0.81.0`
*   **Purpose**: API server, authentication, and data processing
*   **Details**: Python FastAPI application that handles HTTP API requests (port 1323), user authentication, and business logic. Uses SQLite for users/sessions plus metadata indexing, and queries parquet-backed span data with hot+cold merge logic.

#### `junjo-ai-studio-frontend`
*   **Image**: `mdrideout/junjo-ai-studio-frontend:0.81.0`
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
*   **Purpose**: Example showing how to integrate Junjo AI Studio into your Python applications
*   **Details**: Runs a simple 3-node Junjo workflow (StartNode → IncrementNode → EndNode) in a continuous loop, executing **every 5 seconds**. Each execution generates a complete OpenTelemetry trace showing state changes, node timing, and workflow decision flow. This continuous telemetry stream demonstrates real-time ingestion and visualization.

**What the Demo Does:**
- Executes a workflow that increments a counter
- Sends complete trace data to `junjo-ai-studio-ingestion` via gRPC
- Creates visible workflow runs in the Junjo AI Studio UI every 5 seconds
- Shows how to configure `JunjoServerOtelExporter` in your own applications
- Watch it running: `docker logs -f junjo-app`

**For Production:**
Use `junjo_app/` as a reference implementation. **Remove this service** from `docker-compose.yml` if you don't need the demo running continuously.

---

# Miscellaneous

## SSL Testing with Let's Encrypt Staging

Let's Encrypt rate limits SSL certificate issuance. When setting up a new environment, if you get rate limited, you can use the Let's Encrypt staging environment to avoid production rate limits during testing.

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

1. Download the staging certificates (provide your domain as argument):
   ```bash
   bash download_staging_certs.sh junjo.example.com
   ```

   Or if you have `JUNJO_PROD_FRONTEND_URL` set in `.env`, the script will extract the domain automatically:
   ```bash
   bash download_staging_certs.sh
   ```

2. Open the `.certs` folder in Finder and double-click the `.pem` files to add them to Keychain Access

3. In Keychain Access, double-click each new certificate and expand the "Trust" section

4. Select "Always Trust" for both certificates

5. Restart your browser (Chrome or Safari)

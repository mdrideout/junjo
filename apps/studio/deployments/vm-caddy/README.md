# Junjo Server - Production VM Deployment Example

This repository walks you through creating a production-ready deployment of Junjo Server that you can run on a cheap VM, allowing your AI applications to send telemetry data for debugging, observability, and workflow analysis.

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

Open `.env` in your editor and replace `your_secret_key` with a new key. You can generate one with the following command:

```bash
openssl rand -base64 48
```

### 3. Run the Application

Start all the services using Docker Compose:

```bash
docker compose up --build
```

This command will build the `junjo-app` image and pull the necessary images for the other services. It may take a few minutes the first time you run it.

### 4. Access the Services

Once all the services are running, you can access them in your browser:

*   **Junjo Server UI**: [http://localhost:5153](http://localhost:5153)

#### Junjo Setup Steps:

1.  Navigate to [http://localhost:5153](http://localhost:5153) and create your user account, then sign in.
2.  Create an [API key](http://localhost:5153/api-keys) in the Junjo Server UI.
3.  Set this key as the `JUNJO_SERVER_API_KEY` environment variable in your `.env` file.
4.  Restart the `junjo-app` container to apply the new API key:
    ```bash
    docker compose restart junjo-app
    ```

> **Troubleshooting:** If you see a "failed to get session" error in the logs or have trouble logging in, try clearing your browser's cookies for `localhost` and restarting the services. This can happen if you have multiple Junjo server projects running on `localhost` and an old session cookie is interfering.

You should see workflow runs appearing in the Junjo Server UI every 5 seconds. You can click on a run to see detailed execution information.

### 5. Stopping the Application

To stop all the services, press `Ctrl+C` in the terminal where `docker compose` is running. To remove the containers and their volumes, run:

```bash
docker compose down -v
```

---

## Production Deployment

Deploy Junjo Server to a cloud VM to provide a centralized observability backend for your AI applications running anywhere. Your applications will connect to your deployed Junjo Server instance via the gRPC ingestion endpoint.

### Domain Configuration

The `JUNJO_PROD_AUTH_DOMAIN` environment variable defines your primary production domain and controls:

1. **Frontend Access**: The web UI domain for viewing workflows
2. **Session Cookies**: Domain-wide authentication (covers all subdomains)
3. **API & gRPC Endpoints**: Subdomain routing for backend services

**Requirements:**
- A wildcard DNS record for your domain (e.g., `*.example.com`)
- Cloudflare API token for automatic SSL (or configure alternative DNS provider)

### Service Endpoints

Assuming `JUNJO_PROD_AUTH_DOMAIN=junjo.example.com`, your deployment will be accessible at:

| Service | URL | Purpose |
|---------|-----|---------|
| **Web UI** | `https://junjo.example.com` | View and debug AI workflow executions |
| **API** | `https://api.junjo.example.com` | Backend HTTP API |
| **Ingestion** | `grpc.junjo.example.com:443` | **Your AI applications send telemetry here** |

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

### Caddy Server / Reverse Proxy

One would typically manage and deploy Caddy (or other reverse proxy) separately from the Junjo Server for their virtual machine. You may have a server-wide docker network and many 
other container services running on the same machine that you'd like to control individually.

This example bundles Caddy **with** the example Junjo App and Junjo Server instance for turn-key demonstration purposes.

The `Caddyfile` can be used as a demonstration for:

- `:80` local and `*.{$JUNJO_PROD_AUTH_DOMAIN}` production deployment
- Cloudflare DNS setup example
- Subdomain service access configuration through Caddy

## Services Architecture

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
*   **Details**: Runs a simple Junjo workflow in a loop, sending OpenTelemetry data to the ingestion service. Use this as a reference when building your own integrations. **Remove this service in production** if you don't need the demo.

## Digital Ocean VM Deployment Example

The following assumes a fresh Digital Ocean Droplet VM with the following configuration:

- Debian 12
- 1GB RAM
- 1vCPU
- 25GB Disk

The following are instructions for baseline server setup and deployment of the Junjo Server and Junjo App.

### SSH into the server

```bash
$ ssh root@[your-ip-address]
```

### Install Docker & Docker Compose

1. Follow [Install Docker Engine on Debian](https://docs.docker.com/engine/install/debian/) instructions.
2. Install rsync `sudo apt install rsync`
3. Disconnect from ssh for next steps

### Copy Files & Launch

These commands will copy the files from your machine to the remote server.

```bash
# Copy via rsync (ssh must be disconnected to execute)
# Exclude hidden files except for .env.example
$ rsync -avz --delete -e ssh --include='.env.example' --exclude='.??*' ~/path/on/local/machine/ root@[your-ip-address]:folder_name/

# ssh into the server again
$ ssh root@[your-ip-address]

# cd into to the folder you uploaded the project to
$ cd ~/folder_name

# Verify all files were copied correctly
$ ls -a

# Copy the .env.example file and rename it to .env
$ cp .env.example .env

# Edit the .env file and update the required environment variables (the JUNJO_SERVER_API_KEY can be added after the Junjo Server is running)
$ sudo vi .env

# Exit the vi text editor with escape key, then type :wq to save and quit

# Pull the latest Junjo Server images and launch the docker compose configuration in detached mode so it runs in the background
# This will start all of the services
$ docker compose pull && docker compose up -d --build

# Create & Set the Junjo Server API Key
# 1. Access the frontend and create an API key.
# 2. Edit the .env file again and set the JUNJO_SERVER_API_KEY
# 3. Restart the Junjo App so that it picks up the new API key and can deliver telemetry to the Junjo Server
$ docker compose restart junjo-app

# List containers
$ docker container ls

# Watch logs of the container (check caddy for successful SSL)
$ docker logs -f caddy
```

## Caddy SSL Staging / Testing

Let's Encrypt rate limits SSL certificate issuance. When setting up a new environment it is recommended to use the Let's Encrypt staging environment to avoid rate limits during testing. Just a few `docker compose down -v` and `docker compose up -d --build` commands can exhaust your rate limit.

To use Let's Encrypt staging certificates, uncomment the following line in your `.env` file.

```yaml
# === FOR SSL TESTING ============================================================================>
# ...
JUNJO_LETS_ENCRYPT_STAGING_CA_DIRECTIVE="ca https://acme-staging-v02.api.letsencrypt.org/directory"
```

Caddy will then automatically use the Let's Encrypt staging environment when generating certificates.

Without manually trusting these staging certificates, you will see a "Your connection is not private" warning in your browser.

Follow the instructions below for downloading and trusting the staging certificates on a MacOS system, allowing complete testing.

### Staging SSL Testing Instructions:

To test your setup, you can add a staging certificate to your MacOS Keychain Access and trust it. The following steps will guide you through the process:

1. Run the certificate download script:

```bash
# Download the staging certificates to the .certs directory in this project directory
$ bash download_staging_certs.sh
```

2. Open the `.certs` folder in Finder and double-click on the `.pem` files to add them to "Keychain Access".
3. Inside Keychain Access, double-click the new certificates and expand the "Trust" section
4. Select "Always Trust" on both of them
5. Restart chrome or safari and you should be able to access the site


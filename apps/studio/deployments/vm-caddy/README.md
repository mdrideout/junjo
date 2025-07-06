# Junjo Server Deployment Example

This repository provides a complete, deployable example of a custom Junjo application running alongside the Junjo Server in a Docker Compose environment. It is designed to be a starting point for users who want to build and deploy their own Junjo-powered applications.

## Prerequisites

*   [Docker](https://docs.docker.com/get-docker/)
*   [Docker Compose](https://docs.docker.com/compose/install/)

## Getting Started

### 1. Clone the Repository

```bash
git clone https://github.com/mdrideout/junjo-server-deployment-example.git
cd junjo-server-deployment-example
```

### 2. Configure Environment Variables

Copy the example environment file and update it with your own secret key.

```bash
cp .env.example .env
```

Open `.env` in your editor and replace `your-super-secret-key` with a new key. You can generate one with the following command:

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
*   **Jaeger UI for Tracing**: [http://localhost/jaeger](http://localhost/jaeger)

#### Junjo Setup Steps:

1.  Navigate to [http://localhost:5153](http://localhost:5153) and create your user account, then sign in.
2.  Create an [API key](http://localhost:5153/api-keys) in the Junjo Server UI.
3.  Set this key as the `JUNJO_SERVER_API_KEY` environment variable in your `.env` file.
4.  Restart the `junjo-app` container to apply the new API key:
    ```bash
    docker compose restart junjo-app
    ```

> **Troubleshooting:** If you see a "failed to get session" error in the logs or have trouble logging in, try clearing your browser's cookies for `localhost` and restarting the services. This can happen if you have multiple Junjo server projects running on `localhost` and an old session cookie is interfering.

You should see workflow runs appearing in the Junjo Server UI every 5 seconds. You can click on a run to see the detailed trace in Jaeger.

### 5. Stopping the Application

To stop all the services, press `Ctrl+C` in the terminal where `docker compose` is running. To remove the containers and their volumes, run:

```bash
docker compose down -v
```

## Production Deployment

The `JUNJO_PROD_AUTH_DOMAIN` environment variable is used to define the primary production domain. The domain sets:

1. The Junjo Server frontend access domain.
2. The session cookie domain + subdomains (all subdomains are covered)
   1. Requires a wildcard DNS record.

### Accessing Production Services:

Assuming the `JUNJO_PROD_AUTH_DOMAIN` is set to `junjo.example.com`, you can access the services at:

*   Junjo Server UI: [https://junjo.example.com](https://junjo.example.com)
*   Jaeger UI: [https://junjo.example.com/jaeger](https://junjo.example.com/jaeger)
*   Junjo Server API: [https://api.junjo.example.com](https://api.junjo.example.com)
*   Junjo Server gRPC: [https://grpc.junjo.example.com](https://grpc.junjo.example.com)
    *   This is the endpoint for delivering open telemetry data to Junjo Server from your python application setup with a `JunjoServerOtelExporter`

### Caddy Server / Reverse Proxy

One would typically manage and deploy Caddy (or other reverse proxy) separately from the Junjo Server for their virtual machine. You may have a server-wide docker network and many 
other container services running on the same machine that you'd like to control individually.

This example bundles Caddy **with** the example Junjo App and Junjo Server instance only for demonstration purposes.

The `Caddyfile` can be used as a demonstration for:

- Secure Jaeger access via forward_auth
- `:80` local and `*.{$JUNJO_PROD_AUTH_DOMAIN}` production deployment
- Cloudflare DNS setup example
- Subdomain service access configuration through Caddy

## Services

### `junjo-app`

*   **Description**: A custom Python application that runs a simple Junjo workflow in a loop.
*   **Source**: See the `junjo_app/` directory.
*   **Details**: This application is configured to send OpenTelemetry data to the `junjo-server-backend` via gRPC. This allows you to see the workflow's execution traces in the Junjo Server UI.

### `junjo-server-backend`

*   **Description**: The backend service for the Junjo Server.
*   **Image**: `mdrideout/junjo-server-backend:latest`
*   **Details**: This service receives telemetry data, stores it, and serves the API for the frontend.

### `junjo-server-frontend`

*   **Description**: The web interface for the Junjo Server.
*   **Image**: `mdrideout/junjo-server-frontend:latest`
*   **Details**: This service provides the user interface for viewing workflow runs and telemetry.

### `junjo-jaeger`

*   **Description**: The Jaeger all-in-one instance for distributed tracing.
*   **Image**: `jaegertracing/jaeger:2.3.0`
*   **Details**: The Junjo Server is integrated with Jaeger to provide detailed traces of workflow executions.

### `caddy`

*   **Description**: A modern, powerful reverse proxy.
*   **Source**: [`caddy/`](caddy/)
*   **Details**: Caddy routes incoming traffic to the appropriate services based on the path. The configuration can be found in the [`caddy/Caddyfile`](caddy/Caddyfile). For production use, you would replace `localhost` with your domain name, and Caddy would automatically handle HTTPS for you.

## Digital Ocean VM Setup Example

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
$ docker compose pull && docker compose up -d --build

# List containers
$ docker container ls

# Watch logs of the container (check caddy for successful SSL)
$ docker logs -f caddy
```

## Caddy SSL Staging / Testing

Let's Encrypt rate limits SSL certificate issuance. When setting up a new environment it is recommended to use the Let's Encrypt staging environment to avoid rate limits during testing. Just a few `docker compose down -v` and `docker compose up -d --build` commands can exhaust your rate limit.

The [Caddyfile](caddy/Caddyfile) includes a commented out line for using the Let's Encrypt staging environment. To use it, uncomment the line.

```yaml
# --- FOR SSL TESTING ---
# ...
# ca https://acme-staging-v02.api.letsencrypt.org/directory
```

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


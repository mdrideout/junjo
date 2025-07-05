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

The `PROD_AUTH_DOMAIN` environment variable is used to define the primary production domain. The domain sets:

1. The Junjo Server frontend access domain.
2. The session cookie domain + subdomains (all subdomains are covered)
   1. Requires a wildcard DNS record.

### Accessing Production Services:

Assuming the `PROD_AUTH_DOMAIN` is set to `junjo.example.com`, you can access the services at:

*   Junjo Server UI: [https://junjo.example.com](https://junjo.example.com)
*   Jaeger UI: [https://junjo.example.com/jaeger](https://junjo.example.com/jaeger)
*   Junjo Server API: [https://api.junjo.example.com](https://api.junjo.example.com)
*   Junjo Server gRPC: [https://grpc.junjo.example.com](https://grpc.junjo.example.com)
    *   This is the endpoint for delivering open telemetry data to Junjo Server from your python application setup with a `JunjoServerOtelExporter`


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

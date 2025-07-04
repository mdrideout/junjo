# Junjo Server

> 順序 - Japanese Translation: order, sequence, procedure

Junjo Server is an opentelemetry ingestion server and AI graph workflow debugging interface designed to be run in Docker and deployed to a virtual machine.

This is a companion telemetry server for the [Junjo Python SDK](https://github.com/mdrideout/junjo).

<img src="https://python-api.junjo.ai/_images/junjo-screenshot.png" width="600" />

_junjo frontend screenshot_

### Components

This repository contains everything that runs the Junjo telemetry server and user interface.

- Backend API and gRPC server
- Jaeger server to demonstrate full opentelemetry span compatibility
- Frontend interface
- Authentication via Caddy reverse proxy forward with and session cookies

## Use & Deployment

The backend service is automatically built and deployed to Docker Hub whenever a new release is published on GitHub.

- Backend Docker Container Image: [https://hub.docker.com/r/mdrideout/junjo-server-backend](https://hub.docker.com/r/mdrideout/junjo-server-backend)
- Frontend Docker Container Image: [https://hub.docker.com/r/mdrideout/junjo-server-frontend](https://hub.docker.com/r/mdrideout/junjo-server-frontend)

### Environment Configuration

Before running the services, you need to set up your environment variables. Copy the example environment file to a new `.env` file:

```bash
cp .env.example .env
```

Then, open the `.env` file and configure the variables as needed. At a minimum, you should set a secure `SESSION_SECRET`. For production, you should also configure `ALLOW_ORIGINS` to match the domain where you are hosting the frontend.

- `BUILD_TARGET`: Should be set to `production` when using the hosted images.
- `SESSION_SECRET`: A long, random string used for securing user sessions.
- `ALLOW_ORIGINS`: A comma-separated list of URLs that are allowed to make requests to the backend API.

### Docker Compose - Hosted Images

To run the pre-built images from Docker Hub in a production-like environment, you can use the `docker-compose.yml` file below. This setup pulls the images directly from the registry, bypassing any local build steps.

This example provides a complete, self-contained setup including the backend, frontend, Jaeger for tracing, and Caddy as a reverse proxy.

```yaml
services:
  junjo-server-backend:
    image: mdrideout/junjo-server-backend:latest # Or specify a version like: v1.2.0
    container_name: junjo-server-backend
    restart: unless-stopped
    volumes:
      - ./dbdata/sqlite:/dbdata/sqlite
      - ./dbdata/duckdb:/dbdata/duckdb
    ports:
      - "1323:1323"
      - "50051:50051"
    networks:
      - junjo-network
    env_file:
      - .env
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:1323/ping"]
      interval: 5s
      timeout: 3s
      retries: 25
      start_period: 5s

  junjo-server-frontend:
    image: mdrideout/junjo-server-frontend:latest # Or specify a version like: v1.2.0
    container_name: junjo-server-frontend
    restart: unless-stopped
    ports:
      - "5153:80" # Exposed port to Nginx mapping
    networks:
      - junjo-network
    depends_on:
      junjo-server-backend:
        condition: service_healthy

  junjo-jaeger:
    image: jaegertracing/jaeger:2.3.0
    container_name: junjo-jaeger
    restart: unless-stopped
    volumes:
      - ./jaeger/config.yml:/jaeger/config.yml # You may need to create this file
      - jaeger_badger_store:/data/jaeger/badger/jaeger
      - jaeger_badger_store_archive:/data/jaeger/badger/jaeger_archive
    command: --config /jaeger/config.yml
    user: root # Currently requires root for writing to the vol (track: https://github.com/jaegertracing/jaeger/issues/6458)
    networks:
      - junjo-network

  caddy:
    image: caddy:2-alpine
    container_name: junjo-caddy
    restart: unless-stopped
    ports:
      - "80:80" # For HTTP -> HTTPS redirect
      - "443:443" # For HTTPS
    volumes:
      - ./Caddyfile:/etc/caddy/Caddyfile # You will need to provide your own Caddyfile
      - caddy_data:/data # Persist Caddy data (certificates)
      - caddy_config:/config # Persist Caddy config
    networks:
      - junjo-network
    depends_on:
      - junjo-server-backend
      - junjo-server-frontend
      - junjo-jaeger

volumes:
  jaeger_badger_store:
  jaeger_badger_store_archive:
  caddy_data:
  caddy_config:

networks:
  junjo-network: # Allow these services to communicate with each other
    driver: bridge

# Network option if you want to use an existing shared server network
# networks:
#   your-network:
#     external: true # not coupled to this compose file
```

### Docker Compose - Self Build

Checkout the [Junjo Server Repository](https://github.com/mdrideout/junjo-server) `docker-compose.yml` file for an example of how to build and run the backend and frontend services yourself.

## Running The Dev Environment

Docker is required for local development so your developer experience mirrors how things work in production.

- **hot reloading** is still supported in both the *frontend* and *backend*. 

### Caddy Server
Caddy is utilized as a reverse proxy to facilitate authentication guarded access to various services.
- This runs in local development mode as part of the development environment build
- It is expected that your virutal machine will have it's own Caddy service running, therefore it is excluded from production builds.

#### Docker Commands

Docker compose can be used to launch the frontend and backend together, with hot reloading for local development.

> Ensure the project root `.env` file contains `BUILD_TARGET=development`

> TIP: `docker compose down -v` is required if node modules or go modules change (installed / uninstalled)

```bash
# Create the network (if it does not already exist)
$ docker network create caddy-proxy-network

# Start the frontend and backend
$ docker compose up --build

# Close and clear volumes
$ docker compose down -v
```

#### Accessing Services

- Frontend: https://localhost:5151
- Backend API: https://localhost:1323/
- Jaeger UI: https://localhost/jaeger 
  - This is routed through Caddy reverse proxy forward_auth for authentication via the Backend API's cookie header validation
# Junjo Server

> 順序 - order, sequence, procedure

The [Junjo Python Library](https://github.com/mdrideout/junjo) is an AI Graph Workflow and state machine framework that makes it easy to build and run structured directed graph workflows that are dynamically traversed by an LLM.

**Junjo Server** is an opentelemetry ingestion server and AI graph workflow debugging interface. This provides telemetry, observability, and a debugging interface for the Junjo Python Library.

If you've struggled to understand what decisions your LLM is making in a chained sequence of events, and what data it is basing its decisions on, Junjo Server is for you. You will gain complete visibility to the state of the application, and every change LLMs make to the application state.

Complex, mission critical AI workflows are made transparent and understandable with Junjo and Junjo Server.

<img src="https://python-api.junjo.ai/_images/junjo-screenshot.png" width="600" />

_Junjo Server Frontend Screenshot_

## Turn-Key Example Repository

**Junjo Server Deployment Example [https://github.com/mdrideout/junjo-server-deployment-example](https://github.com/mdrideout/junjo-server-deployment-example)**.

- _A complete example of a Junjo Server deployment, including a Junjo Python Library application._

**Components:** This repository is orchestrated with [Docker Compose](https://github.com/mdrideout/junjo-server-deployment-example/blob/master/docker-compose.yml). 

- Session cookie authentication
- Junjo Server pre-build images:
  - Docker hub junjo-server-backend: [https://hub.docker.com/r/mdrideout/junjo-server-backend](https://hub.docker.com/r/mdrideout/junjo-server-backend)
  - Docker hub junjo-server-frontend: [https://hub.docker.com/r/mdrideout/junjo-server-frontend](https://hub.docker.com/r/mdrideout/junjo-server-frontend)
- Local development and production environment variable configurability

The [README.md](https://github.com/mdrideout/junjo-server-deployment-example/blob/master/README.md) will walk you through the deployment process on a Digital Ocean Droplet virtual machine (or any VM provider of your choice). You can use this as the basis for your own deployment of Junjo Server.

### VM Resource Requirements

Junjo is designed to be low resource. It uses SQLite, DuckDB, and BadgerDB for storage, which are all low resource embedded databases. It can be run on small affordable virtual machines with as little as **a shared vCPU** and **1GB of RAM**.

## Use & Deployment

Junjo Server is built and deployed to **Docker Hub** whenever a new release is published on GitHub.

- **Backend**: [https://hub.docker.com/r/mdrideout/junjo-server-backend](https://hub.docker.com/r/mdrideout/junjo-server-backend)
- **Frontend**: [https://hub.docker.com/r/mdrideout/junjo-server-frontend](https://hub.docker.com/r/mdrideout/junjo-server-frontend)

### Environment Configuration

Before running the services, you need to set up your environment variables.

Copy the example environment file to a new `.env` file:

```bash
cp .env.example .env
```

The `JUNJO_SERVER_API_KEY` can be created in the Junjo Server frontend interface after you get it intially running.

### Docker Compose - Hosted Images

Below if a brief example of using the Junjo Server pre-built images from Docker Hub.

For a more complete example, checkout the [Junjo Server Deployment Example Repository](https://github.com/mdrideout/junjo-server-deployment-example/blob/master/docker-compose.yml).

```yaml
services:
  junjo-server-backend:
    image: mdrideout/junjo-server-backend:latest
    container_name: junjo-server-backend
    restart: unless-stopped
    volumes:
      - ./.dbdata/sqlite:/dbdata/sqlite
      - ./.dbdata/duckdb:/dbdata/duckdb
    ports:
      - "1323:1323"
      - "50051:50051"
    networks:
      - junjo-network
    env_file:
      - .env
    user: root # requires root for writing to the duckdb vol
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:1323/ping"]
      interval: 5s
      timeout: 3s
      retries: 25
      start_period: 5s

  junjo-server-frontend:
    image: mdrideout/junjo-server-frontend:latest
    container_name: junjo-server-frontend
    restart: unless-stopped
    ports:
      - "5153:80" # Access the frontend at http://localhost:5153
    env_file:
      - .env
    networks:
      - junjo-network
    depends_on:
      junjo-server-backend:
        condition: service_healthy

networks:
  junjo-network:
    driver: bridge

# Network option if you want to use an existing shared server network
# networks:
#   your-network:
#     external: true # not coupled to this compose file
```

## Running The Local Dev Environment

Docker is required for local development so your developer experience mirrors how things work in production.

- **hot reloading** is supported in both the *frontend* and *backend*. 

#### Docker Commands

Docker compose can be used to launch the frontend and backend together, with hot reloading for local development.

> Ensure the project root `.env` file contains `JUNJO_BUILD_TARGET=development`

> TIP: `docker compose down -v` is required if node modules or go modules change (installed / uninstalled)

```bash
# Create the network (if it does not already exist)
$ docker network create junjo-network

# Start the frontend and backend
$ docker compose up --build

# Close and clear volumes
$ docker compose down -v
```

#### Accessing Services (development environment)

- Frontend: https://localhost:5151
- Backend API: https://localhost:1323/

#### Troubleshooting

If you see a "failed to get session" error in the logs or have trouble logging in, try clearing your browser's cookies for `localhost` and restarting the services. This can happen if you have multiple Junjo server projects running on `localhost` and an old session cookie is interfering.
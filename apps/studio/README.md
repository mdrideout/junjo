# Junjo Server

This repository contains everything that runs the Junjo telemetry server and user interface.

- Go Echo API and gRPC server
- Jaeger server
- Caddy reverse proxy
- React frontend

## Frontend

- Vite React SPA

## Backend

- GO echo API and grpc telemetry server [docs](/backend/README.md)
- JWT auth middleware
- JSON auth database
- sqlc for queries to the sqlite data

## Running The Dev Environment

Docker is required for local development so your developer experience mirrors how things work in production.

- **hot reloading** is still supported in both the *frontend* and *backend*. 

### Caddy Server
Caddy is utilized as a reverse proxy to facilitate authentication guarded access to various services.
- This runs in local development mode as part of the development environment build
- It is expected that your virutal machine will have it's own Caddy service running, therefore it is excluded from production builds.

#### .env requirements

- `/backend` .env
- `/frontend` .env

#### Docker Commands

Docker compose can be used to launch the frontend and backend together, with hot reloading for local development.

> Ensure the project root `.env` file contains `BUILD_TARGET=development`

> TIP: `docker compose down -v` is required if node modules or go modules change (installed / uninstalled)

```bash
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



## Authentication

The backend is uses a JWT based authentication guard. The users database is a JSON file of email addresses and passwords. Do not check this file into the github repository.

#### Environment Var: SESSION_SECRET

TODO: Document how this is utilized for signing the sessions.
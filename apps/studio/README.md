# Junjo UI

Repository for the FE + BE of the telemetry UI application.

## Frontend

- Vite React SPA

## Backend

- Go Echo Server
- JWT auth middleware
- JSON auth database
- sqlc for queries to the sqlite data

## Running The Dev Environment

#### .env requirements

- `/backend` .env
- `/frontend` .env

### Without Docker

```bash
# Start the backend with hot reloading
$ air

# Build / run the backend
$ go run main.go
```
# --- 1. Development Stage ---
FROM golang:1.25-alpine AS development

WORKDIR /app

# Install tini for proper signal handling, even in development
RUN apk add --no-cache tini

# Install Air for hot-reloading
RUN go install github.com/air-verse/air@latest

# Install grpc_health_probe for health checks
RUN apk add --no-cache curl && \
    GRPC_HEALTH_PROBE_VERSION=v0.4.24 && \
    curl -sL https://github.com/grpc-ecosystem/grpc-health-probe/releases/download/${GRPC_HEALTH_PROBE_VERSION}/grpc_health_probe-linux-amd64 -o /usr/local/bin/grpc_health_probe && \
    chmod +x /usr/local/bin/grpc_health_probe && \
    apk del curl

# Copy Go module files and download dependencies
COPY go.mod go.sum ./
RUN go mod download

# Copy the rest of the application source code
COPY . .

# Expose the gRPC port
EXPOSE 50051

# Use tini as the entrypoint to ensure signals are forwarded to air
ENTRYPOINT ["/sbin/tini", "--"]

# Command to run the application with hot-reloading
CMD ["air", "-c", ".air.toml"]

# --- 2. Production Stage ---
FROM golang:1.25-alpine AS builder

WORKDIR /app

# Copy Go module files and download dependencies
COPY go.mod go.sum ./
RUN go mod download

# Copy the rest of the application source code
COPY . .

# Build the application
RUN CGO_ENABLED=0 GOOS=linux go build -o /ingestion-service

# --- 3. Final Production Image ---
FROM alpine:latest AS production

WORKDIR /

# Install tini for proper signal handling and grpc_health_probe
RUN apk add --no-cache tini curl && \
    GRPC_HEALTH_PROBE_VERSION=v0.4.24 && \
    curl -sL https://github.com/grpc-ecosystem/grpc-health-probe/releases/download/${GRPC_HEALTH_PROBE_VERSION}/grpc_health_probe-linux-amd64 -o /usr/local/bin/grpc_health_probe && \
    chmod +x /usr/local/bin/grpc_health_probe && \
    apk del curl

# Copy the binary from the builder stage
COPY --from=builder /ingestion-service /ingestion-service

# Expose the gRPC port
EXPOSE 50051

# Use tini as the entrypoint to ensure signals are forwarded correctly
ENTRYPOINT ["/sbin/tini", "--"]

# Command to run the application
CMD ["/ingestion-service"]
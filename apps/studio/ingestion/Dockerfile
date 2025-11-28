# --- 1. Development Stage ---
FROM golang:1.25-alpine AS development

WORKDIR /app

# Install tini for proper signal handling, even in development
# Install gcc, musl-dev, sqlite-dev for CGO (crawshaw.io/sqlite)
RUN apk add --no-cache tini gcc musl-dev sqlite-dev

# Install Air for hot-reloading
RUN go install github.com/air-verse/air@latest

# Install grpc_health_probe for health checks
RUN apk add --no-cache curl unzip && \
    GRPC_HEALTH_PROBE_VERSION=v0.4.24 && \
    curl -sL https://github.com/grpc-ecosystem/grpc-health-probe/releases/download/${GRPC_HEALTH_PROBE_VERSION}/grpc_health_probe-linux-amd64 -o /usr/local/bin/grpc_health_probe && \
    chmod +x /usr/local/bin/grpc_health_probe

# Copy shared proto files
COPY proto/ ../proto/

# Copy Go module files and download dependencies
COPY ingestion/go.mod ingestion/go.sum ./
RUN go mod download

# Copy the rest of the application source code
COPY ingestion/ .

# Install protoc v30.2 and Go protobuf plugins with locked versions
ARG TARGETARCH
RUN PROTOC_VERSION=30.2 && \
    case ${TARGETARCH} in \
        "amd64") PROTOC_ARCH="x86_64" ;; \
        "arm64") PROTOC_ARCH="aarch_64" ;; \
        *) echo "Unsupported architecture: ${TARGETARCH}" && exit 1 ;; \
    esac && \
    curl -LO https://github.com/protocolbuffers/protobuf/releases/download/v${PROTOC_VERSION}/protoc-${PROTOC_VERSION}-linux-${PROTOC_ARCH}.zip && \
    unzip -o protoc-${PROTOC_VERSION}-linux-${PROTOC_ARCH}.zip -d /usr/local bin/protoc && \
    unzip -o protoc-${PROTOC_VERSION}-linux-${PROTOC_ARCH}.zip -d /usr/local 'include/*' && \
    rm protoc-${PROTOC_VERSION}-linux-${PROTOC_ARCH}.zip && \
    go install google.golang.org/protobuf/cmd/protoc-gen-go@v1.36.10 && \
    go install google.golang.org/grpc/cmd/protoc-gen-go-grpc@v1.5.1

# Generate proto files from shared proto directory
RUN protoc \
    -I../proto \
    --go_out=./proto_gen \
    --go-grpc_out=./proto_gen \
    ../proto/*.proto

# Expose ports
# Public OTLP endpoint (authenticated via API key - mapped to host)
EXPOSE 50051
# Internal gRPC for span reading (NOT mapped to host - internal Docker network only)
EXPOSE 50052

# Use tini as the entrypoint to ensure signals are forwarded to air
ENTRYPOINT ["/sbin/tini", "--"]

# Command to run the application with hot-reloading
CMD ["air", "-c", ".air.toml"]

# --- 2. Production Stage ---
FROM golang:1.25-alpine AS builder

WORKDIR /app

# Install curl and unzip for downloading protoc
# Install gcc, musl-dev, sqlite-dev for CGO (crawshaw.io/sqlite)
RUN apk add --no-cache curl unzip gcc musl-dev sqlite-dev

# Copy shared proto files
COPY proto/ ../proto/

# Copy Go module files and download dependencies
COPY ingestion/go.mod ingestion/go.sum ./
RUN go mod download

# Copy the rest of the application source code
COPY ingestion/ .

# Install protoc v30.2 and Go protobuf plugins with locked versions
ARG TARGETARCH
RUN PROTOC_VERSION=30.2 && \
    case ${TARGETARCH} in \
        "amd64") PROTOC_ARCH="x86_64" ;; \
        "arm64") PROTOC_ARCH="aarch_64" ;; \
        *) echo "Unsupported architecture: ${TARGETARCH}" && exit 1 ;; \
    esac && \
    curl -LO https://github.com/protocolbuffers/protobuf/releases/download/v${PROTOC_VERSION}/protoc-${PROTOC_VERSION}-linux-${PROTOC_ARCH}.zip && \
    unzip -o protoc-${PROTOC_VERSION}-linux-${PROTOC_ARCH}.zip -d /usr/local bin/protoc && \
    unzip -o protoc-${PROTOC_VERSION}-linux-${PROTOC_ARCH}.zip -d /usr/local 'include/*' && \
    rm protoc-${PROTOC_VERSION}-linux-${PROTOC_ARCH}.zip && \
    go install google.golang.org/protobuf/cmd/protoc-gen-go@v1.36.10 && \
    go install google.golang.org/grpc/cmd/protoc-gen-go-grpc@v1.5.1

# Generate proto files from shared proto directory (defense in depth)
# This ensures Docker images always have fresh proto files even if pre-commit hook was skipped
RUN protoc \
    -I../proto \
    --go_out=./proto_gen \
    --go-grpc_out=./proto_gen \
    ../proto/*.proto

# Build the application with CGO enabled for SQLite
RUN CGO_ENABLED=1 GOOS=linux go build -o /ingestion

# --- 3. Final Production Image ---
FROM alpine:latest AS production

WORKDIR /

# Install tini for proper signal handling, sqlite-libs for runtime, and grpc_health_probe
RUN apk add --no-cache tini sqlite-libs curl && \
    GRPC_HEALTH_PROBE_VERSION=v0.4.24 && \
    curl -sL https://github.com/grpc-ecosystem/grpc-health-probe/releases/download/${GRPC_HEALTH_PROBE_VERSION}/grpc_health_probe-linux-amd64 -o /usr/local/bin/grpc_health_probe && \
    chmod +x /usr/local/bin/grpc_health_probe && \
    apk del curl

# Copy the binary from the builder stage
COPY --from=builder /ingestion /ingestion

# Expose ports
# Public OTLP endpoint (authenticated via API key - mapped to host)
EXPOSE 50051
# Internal gRPC for span reading (NOT mapped to host - internal Docker network only)
EXPOSE 50052

# Use tini as the entrypoint to ensure signals are forwarded correctly
ENTRYPOINT ["/sbin/tini", "--"]

# Command to run the application
CMD ["/ingestion"]
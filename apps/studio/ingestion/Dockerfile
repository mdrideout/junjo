# Build stage
FROM rust:1.85-slim-bookworm AS builder

# Install the contract-locked protobuf compiler for proto compilation.
RUN apt-get update && apt-get install -y \
    curl unzip \
    && rm -rf /var/lib/apt/lists/*

ARG TARGETARCH
RUN PROTOC_VERSION=30.2 && \
    case "${TARGETARCH}" in \
      amd64) PROTOC_ARCH=x86_64; PROTOC_SHA256=327e9397c6fb3ea2a542513a3221334c6f76f7aa524a7d2561142b67b312a01f ;; \
      arm64) PROTOC_ARCH=aarch_64; PROTOC_SHA256=a3173ea338ef91b1605b88c4f8120d6c8ccf36f744d9081991d595d0d4352996 ;; \
      *) echo "Unsupported architecture: ${TARGETARCH}" >&2; exit 1 ;; \
    esac && \
    PROTOC_ZIP="protoc-${PROTOC_VERSION}-linux-${PROTOC_ARCH}.zip" && \
    curl -fsSLO "https://github.com/protocolbuffers/protobuf/releases/download/v${PROTOC_VERSION}/${PROTOC_ZIP}" && \
    echo "${PROTOC_SHA256}  ${PROTOC_ZIP}" | sha256sum -c - && \
    unzip -q "${PROTOC_ZIP}" -d /usr/local bin/protoc 'include/*' && \
    rm "${PROTOC_ZIP}" && \
    test "$(protoc --version)" = "libprotoc 30.2"

# Install grpc_health_probe for Compose healthchecks.
RUN GRPC_HEALTH_PROBE_VERSION=v0.4.35 && \
    case $(dpkg --print-architecture) in \
        "amd64") ARCH="amd64" ;; \
        "arm64") ARCH="arm64" ;; \
        *) echo "Unsupported architecture" && exit 1 ;; \
    esac && \
    curl -fsSL -o /bin/grpc_health_probe \
        "https://github.com/grpc-ecosystem/grpc-health-probe/releases/download/${GRPC_HEALTH_PROBE_VERSION}/grpc_health_probe-linux-${ARCH}" && \
    chmod +x /bin/grpc_health_probe

WORKDIR /app

# Copy manifests first for dependency caching
COPY ingestion/Cargo.toml ingestion/Cargo.lock ./
COPY ingestion/build.rs ./
# Copy shared proto directory (build.rs uses ../proto/ path)
COPY proto/ /proto/

# Create dummy src to build dependencies
RUN mkdir src && \
    echo "fn main() {}" > src/main.rs && \
    cargo build --release && \
    rm -rf src

# Copy actual source code
COPY ingestion/src/ src/

# Build for release (touch main.rs to force rebuild)
RUN touch src/main.rs && cargo build --release

# ============================================================
# Development stage (with cargo-watch for hot reloading)
# ============================================================
FROM rust:1.85-slim-bookworm AS development

RUN apt-get update && apt-get install -y \
    curl unzip \
    && rm -rf /var/lib/apt/lists/*

ARG TARGETARCH
RUN PROTOC_VERSION=30.2 && \
    case "${TARGETARCH}" in \
      amd64) PROTOC_ARCH=x86_64; PROTOC_SHA256=327e9397c6fb3ea2a542513a3221334c6f76f7aa524a7d2561142b67b312a01f ;; \
      arm64) PROTOC_ARCH=aarch_64; PROTOC_SHA256=a3173ea338ef91b1605b88c4f8120d6c8ccf36f744d9081991d595d0d4352996 ;; \
      *) echo "Unsupported architecture: ${TARGETARCH}" >&2; exit 1 ;; \
    esac && \
    PROTOC_ZIP="protoc-${PROTOC_VERSION}-linux-${PROTOC_ARCH}.zip" && \
    curl -fsSLO "https://github.com/protocolbuffers/protobuf/releases/download/v${PROTOC_VERSION}/${PROTOC_ZIP}" && \
    echo "${PROTOC_SHA256}  ${PROTOC_ZIP}" | sha256sum -c - && \
    unzip -q "${PROTOC_ZIP}" -d /usr/local bin/protoc 'include/*' && \
    rm "${PROTOC_ZIP}" && \
    test "$(protoc --version)" = "libprotoc 30.2"

# Install cargo-watch for hot reloading
RUN cargo install cargo-watch --locked

# Install grpc_health_probe for Compose healthchecks.
RUN GRPC_HEALTH_PROBE_VERSION=v0.4.35 && \
    case $(dpkg --print-architecture) in \
        "amd64") ARCH="amd64" ;; \
        "arm64") ARCH="arm64" ;; \
        *) echo "Unsupported architecture" && exit 1 ;; \
    esac && \
    curl -fsSL -o /bin/grpc_health_probe \
        "https://github.com/grpc-ecosystem/grpc-health-probe/releases/download/${GRPC_HEALTH_PROBE_VERSION}/grpc_health_probe-linux-${ARCH}" && \
    chmod +x /bin/grpc_health_probe

WORKDIR /app

# Copy manifests for dependency caching (these will be overwritten by volume mount)
COPY ingestion/Cargo.toml ingestion/Cargo.lock ./
COPY ingestion/build.rs ./
# Copy shared proto directory (build.rs uses ../proto/ path)
COPY proto/ /proto/

# Fetch dependencies only (no compilation, no proto generation)
# This avoids caching generated proto code in the image layer, which would
# cause stale code issues when the volume is recreated from the image.
RUN mkdir src && \
    echo "fn main() {}" > src/main.rs && \
    cargo fetch && \
    rm -rf src target

# Copy actual source code (will be overwritten by volume mount in compose)
COPY ingestion/src/ src/

# Create data directories (needed for development mode)
RUN mkdir -p /app/.dbdata/spans/wal /app/.dbdata/spans/parquet

# Container defaults for local Compose paths and service ports.
ENV INTERNAL_GRPC_PORT=50052
ENV GRPC_PORT=26155
ENV WAL_DIR=/app/.dbdata/spans/wal
ENV SNAPSHOT_PATH=/app/.dbdata/spans/hot_snapshot.parquet
ENV PARQUET_OUTPUT_DIR=/app/.dbdata/spans/parquet
ENV JUNJO_LOG_LEVEL=debug
ENV RUST_BACKTRACE=1

EXPOSE 26155 50052

# Use cargo-watch for hot reloading in development
# -i .dbdata ignores the data directory to prevent restart loops when WAL/parquet files change
CMD ["cargo", "watch", "-i", ".dbdata", "-i", "target", "-w", "src", "-w", "/proto", "-w", "Cargo.toml", "-w", "build.rs", "-x", "run"]

# ============================================================
# Production stage (minimal runtime image)
# ============================================================
FROM debian:bookworm-slim AS production

LABEL org.opencontainers.image.source="https://github.com/mdrideout/junjo" \
      org.opencontainers.image.licenses="Apache-2.0"

COPY LICENSE THIRD_PARTY_NOTICES.md /usr/share/licenses/junjo-ai-studio/
COPY licenses/ingestion-production.json /usr/share/licenses/junjo-ai-studio/

RUN apt-get update && apt-get install -y \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy binary and health probe from builder
COPY --from=builder /app/target/release/ingestion /app/ingestion
COPY --from=builder /bin/grpc_health_probe /bin/grpc_health_probe

# Create data directories
RUN mkdir -p /app/.dbdata/wal /app/.dbdata/parquet

# Container defaults for local Compose paths and service ports.
ENV INTERNAL_GRPC_PORT=50052
ENV GRPC_PORT=26155
ENV WAL_DIR=/app/.dbdata/spans/wal
ENV SNAPSHOT_PATH=/app/.dbdata/spans/hot_snapshot.parquet
ENV PARQUET_OUTPUT_DIR=/app/.dbdata/spans/parquet
ENV JUNJO_LOG_LEVEL=info

EXPOSE 26155 50052

CMD ["/app/ingestion"]

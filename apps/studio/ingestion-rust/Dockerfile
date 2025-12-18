# Build stage
FROM rust:1.85-slim-bookworm AS builder

# Install protobuf compiler for proto compilation
RUN apt-get update && apt-get install -y \
    protobuf-compiler \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install grpc_health_probe
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
COPY ingestion-rust/Cargo.toml ingestion-rust/Cargo.lock ./
COPY ingestion-rust/build.rs ./
COPY ingestion-rust/proto/ proto/

# Create dummy src to build dependencies
RUN mkdir src && \
    echo "fn main() {}" > src/main.rs && \
    cargo build --release && \
    rm -rf src

# Copy actual source code
COPY ingestion-rust/src/ src/

# Build for release (touch main.rs to force rebuild)
RUN touch src/main.rs && cargo build --release

# ============================================================
# Development stage (with cargo-watch for hot reloading)
# ============================================================
FROM rust:1.85-slim-bookworm AS development

RUN apt-get update && apt-get install -y \
    protobuf-compiler \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install cargo-watch for hot reloading
RUN cargo install cargo-watch --locked

# Install grpc_health_probe
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
COPY ingestion-rust/Cargo.toml ingestion-rust/Cargo.lock ./
COPY ingestion-rust/build.rs ./
COPY ingestion-rust/proto/ proto/

# Fetch dependencies only (no compilation, no proto generation)
# This avoids caching generated proto code in the image layer, which would
# cause stale code issues when the volume is recreated from the image.
RUN mkdir src && \
    echo "fn main() {}" > src/main.rs && \
    cargo fetch && \
    rm -rf src target

# Copy actual source code (will be overwritten by volume mount in compose)
COPY ingestion-rust/src/ src/

# Create data directories (needed for development mode)
RUN mkdir -p /app/.dbdata/spans/wal /app/.dbdata/spans/parquet

# Default environment - paths only, tunables come from .env or config.rs defaults
ENV GRPC_PORT=50051
ENV INTERNAL_GRPC_PORT=50052
ENV WAL_DIR=/app/.dbdata/spans/wal
ENV SNAPSHOT_PATH=/app/.dbdata/spans/hot_snapshot.parquet
ENV PARQUET_OUTPUT_DIR=/app/.dbdata/spans/parquet
ENV JUNJO_LOG_LEVEL=debug
ENV RUST_BACKTRACE=1

EXPOSE 50051 50052

# Use cargo-watch for hot reloading in development
# -i .dbdata ignores the data directory to prevent restart loops when WAL/parquet files change
CMD ["cargo", "watch", "-i", ".dbdata", "-i", "target", "-x", "run"]

# ============================================================
# Production stage (minimal runtime image)
# ============================================================
FROM debian:bookworm-slim AS production

RUN apt-get update && apt-get install -y \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy binary and health probe from builder
COPY --from=builder /app/target/release/ingestion-rust /app/ingestion-rust
COPY --from=builder /bin/grpc_health_probe /bin/grpc_health_probe

# Create data directories
RUN mkdir -p /app/.dbdata/wal /app/.dbdata/parquet

# Default environment - paths only, tunables come from .env or config.rs defaults
ENV GRPC_PORT=50051
ENV INTERNAL_GRPC_PORT=50052
ENV WAL_DIR=/app/.dbdata/spans/wal
ENV SNAPSHOT_PATH=/app/.dbdata/spans/hot_snapshot.parquet
ENV PARQUET_OUTPUT_DIR=/app/.dbdata/spans/parquet
ENV JUNJO_LOG_LEVEL=info

EXPOSE 50051 50052

CMD ["/app/ingestion-rust"]

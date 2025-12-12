# Multi-stage Dockerfile for Junjo Ingestion Service (Rust)
# Supports both development and production builds

# =============================================================================
# Base stage with Rust toolchain
# =============================================================================
FROM rust:1.91-slim-bookworm AS base

# Install protobuf compiler and build essentials for gRPC code generation
RUN apt-get update && apt-get install -y \
    protobuf-compiler \
    libprotobuf-dev \
    pkg-config \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# =============================================================================
# Development stage with cargo-watch for hot-reloading
# =============================================================================
FROM base AS development

# Install cargo-watch for hot-reloading
RUN cargo install cargo-watch

# Copy source code (from ingestion-rust subdirectory via context)
COPY ingestion-rust/ .

# Build in debug mode
RUN cargo build

# Default command with hot-reloading
CMD ["cargo", "watch", "-x", "run"]

# =============================================================================
# Builder stage for production
# =============================================================================
FROM base AS builder

# Create a dummy project to cache dependencies
RUN cargo new --bin junjo-ingestion
WORKDIR /app/junjo-ingestion

# Copy dependency files first (from ingestion-rust subdirectory)
COPY ingestion-rust/Cargo.toml ingestion-rust/Cargo.lock ./

# Build dependencies only (this layer will be cached)
RUN cargo build --release 2>/dev/null || true

# Copy actual source code
COPY ingestion-rust/ .

# Touch main.rs to ensure rebuild with actual code
RUN touch src/main.rs

# Build release binary
RUN cargo build --release

# Install grpc_health_probe for health checks
RUN apt-get update && apt-get install -y wget && \
    GRPC_HEALTH_PROBE_VERSION=v0.4.25 && \
    wget -qO/bin/grpc_health_probe https://github.com/grpc-ecosystem/grpc-health-probe/releases/download/${GRPC_HEALTH_PROBE_VERSION}/grpc_health_probe-linux-amd64 && \
    chmod +x /bin/grpc_health_probe && \
    rm -rf /var/lib/apt/lists/*

# =============================================================================
# Production stage with minimal runtime
# =============================================================================
FROM debian:bookworm-slim AS production

# Install required runtime libraries
RUN apt-get update && apt-get install -y \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy binary from builder
COPY --from=builder /app/junjo-ingestion/target/release/junjo-ingestion /app/junjo-ingestion

# Copy health probe
COPY --from=builder /bin/grpc_health_probe /bin/grpc_health_probe

# Create non-root user
RUN useradd -r -s /bin/false junjo && \
    mkdir -p /app/.dbdata && \
    chown -R junjo:junjo /app

USER junjo

# Expose ports
EXPOSE 50051 50052

# Health check
HEALTHCHECK --interval=5s --timeout=3s --retries=5 --start-period=5s \
    CMD ["/bin/grpc_health_probe", "-addr=localhost:50052"]

# Run the service
CMD ["/app/junjo-ingestion"]

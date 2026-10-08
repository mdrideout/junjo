# Junjo AI Studio application image: the backend binary and the built UI.
#
# Build context: apps/studio (the same context ingestion uses), so the shared
# proto directory, the frontend, and the license inventories are available.

# ============================================================
# UI build stage
# ============================================================
FROM node:22-bookworm-slim AS ui

WORKDIR /app
COPY frontend/package*.json ./
RUN npm ci

COPY frontend/ .
RUN npm run build

# Compress each text file once. The backend sends a compressed sibling to a
# browser that accepts it and never compresses per request.
RUN node scripts/precompress.mjs dist

# ============================================================
# Backend build stage
# ============================================================
FROM rust:1.99-slim-bookworm AS builder

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

WORKDIR /app/backend

# Shared proto directory (server/build.rs uses ../../proto).
COPY proto/ /app/proto/

# Manifests and schema first, for dependency caching.
COPY backend/Cargo.toml backend/Cargo.lock ./
COPY backend/evidence/Cargo.toml evidence/
COPY backend/server/Cargo.toml backend/server/build.rs server/
COPY backend/schema/ schema/

# Build dependencies against placeholder sources.
RUN mkdir -p evidence/src server/src && \
    touch evidence/src/lib.rs && \
    echo "fn main() {}" > server/src/main.rs && \
    cargo build --release --locked --package junjo-backend && \
    rm -rf evidence/src server/src

COPY backend/evidence/src/ evidence/src/
COPY backend/server/src/ server/src/

RUN touch evidence/src/lib.rs server/src/main.rs && \
    cargo build --release --locked --package junjo-backend

# ============================================================
# Development stage (cargo-watch for hot reloading)
# ============================================================
# The API only. In development the Vite server serves the UI and proxies API
# requests here.
FROM rust:1.99-slim-bookworm AS development

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

WORKDIR /app/backend

# Shared proto directory (server/build.rs uses ../../proto). Compose mounts
# the working copy over it.
COPY proto/ /app/proto/

# Manifests, schema, and sources. Compose mounts the working copies over them.
COPY backend/Cargo.toml backend/Cargo.lock ./
COPY backend/evidence/ evidence/
COPY backend/server/ server/
COPY backend/schema/ schema/

# Fetch dependencies only. Compiling here would cache generated proto code in
# the image layer, which goes stale when the target volume is recreated.
RUN cargo fetch --locked

COPY backend/dev-entrypoint.sh /usr/local/bin/backend-dev
RUN chmod +x /usr/local/bin/backend-dev

RUN mkdir -p /app/.dbdata

# Container defaults for local Compose paths.
ENV JUNJO_SQLITE_PATH=/app/.dbdata/sqlite/junjo.db
ENV JUNJO_METADATA_DB_PATH=/app/.dbdata/sqlite/metadata.db
ENV JUNJO_PARQUET_STORAGE_PATH=/app/.dbdata/spans/parquet
ENV JUNJO_LOG_LEVEL=debug
ENV RUST_BACKTRACE=1

# HTTP API
EXPOSE 26154
# Internal gRPC for API key validation (internal Docker network only)
EXPOSE 50053

# Use cargo-watch for hot reloading in development. The entrypoint owns
# signal forwarding so the backend process can finish its shutdown.
CMD ["/usr/local/bin/backend-dev"]

# ============================================================
# Production stage (minimal runtime image)
# ============================================================
FROM debian:bookworm-slim AS production

LABEL org.opencontainers.image.source="https://github.com/mdrideout/junjo" \
      org.opencontainers.image.licenses="Apache-2.0"

COPY LICENSE THIRD_PARTY_NOTICES.md /usr/share/licenses/junjo-ai-studio/
COPY licenses/backend-production.json /usr/share/licenses/junjo-ai-studio/
COPY licenses/frontend-production.json /usr/share/licenses/junjo-ai-studio/

WORKDIR /app

COPY --from=builder /app/backend/target/release/junjo-backend /app/junjo-backend
COPY --from=ui /app/dist /app/ui

RUN mkdir -p /app/.dbdata

# Container defaults for local Compose paths.
ENV JUNJO_UI_DIR=/app/ui
ENV JUNJO_SQLITE_PATH=/app/.dbdata/sqlite/junjo.db
ENV JUNJO_METADATA_DB_PATH=/app/.dbdata/sqlite/metadata.db
ENV JUNJO_PARQUET_STORAGE_PATH=/app/.dbdata/spans/parquet

# Studio UI and HTTP API (published by Compose)
EXPOSE 26154
# Internal gRPC for API key validation (internal Docker network only)
EXPOSE 50053

CMD ["/app/junjo-backend"]

# Stage 1: Base - Install dependencies using uv
FROM python:3.13-slim-trixie AS base

# Install build dependencies and tools using apt-get
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    libffi-dev \
    curl \
    unzip \
    && rm -rf /var/lib/apt/lists/*

# Install protoc v30.2 for consistency (Python uses grpcio-tools but scripts may need protoc)
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
    rm protoc-${PROTOC_VERSION}-linux-${PROTOC_ARCH}.zip

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Set working directory
WORKDIR /app

# Copy shared proto files (needed for code generation)
COPY proto/ ../proto/

# Copy dependency files
COPY backend/pyproject.toml backend/uv.lock* ./

# Install dependencies into virtual environment
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-install-project --no-dev

# Stage 2: Production - Final image
FROM python:3.13-slim-trixie AS production

# Install tini and libstdc++6 using apt-get
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    tini \
    libstdc++6 \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy virtual environment from base stage
COPY --from=base /app/.venv ./.venv

# Set PATH to use virtual environment
ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH=/app

# Copy application code first
COPY backend/app ./app

# Copy proto generation script and shared proto files
COPY backend/scripts/generate_proto.sh /tmp/generate_proto.sh
COPY proto/ ../proto/

# Generate proto files using unified script
RUN chmod +x /tmp/generate_proto.sh && \
    /tmp/generate_proto.sh /app/app/proto_gen /app/../proto && \
    rm /tmp/generate_proto.sh

# Copy Alembic configuration and migrations
COPY backend/alembic.ini ./alembic.ini
COPY backend/migrations ./migrations

# Copy entrypoint script
COPY backend/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Create data directory
RUN mkdir -p ./.dbdata

# Expose ports
# HTTP API (public - mapped to host in docker-compose.yml)
EXPOSE 1323
# Internal gRPC for API key validation (NOT mapped to host - internal Docker network only)
EXPOSE 50053

# Use tini with entrypoint script for proper signal handling and migrations
ENTRYPOINT ["/usr/bin/tini", "--", "/entrypoint.sh"]

# Run uvicorn
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "1323"]

# Stage 3: Development - Add dev dependencies and hot reload
FROM production AS development

# Override CMD for hot reload
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "1323", "--reload"]
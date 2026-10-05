# Benchmark-only image for auth_backend_proxy.py, the counting and fault proxy
# in front of the backend's internal ValidateApiKey service. Not released.
#
# Build context: apps/studio (the context the Studio services use), so the
# shared proto directory is available.
FROM python:3.13-slim-trixie

RUN apt-get update && \
    apt-get install -y --no-install-recommends tini && \
    rm -rf /var/lib/apt/lists/*

# Install the same immutable uv release used by repository and hosting builds.
COPY --from=ghcr.io/astral-sh/uv:0.11.7@sha256:240fb85ab0f263ef12f492d8476aa3a2e4e1e333f7d67fbdd923d00a506a516a /uv /bin/

WORKDIR /benchmark

# Install the proxy's locked dependencies only.
COPY ingestion/benchmarks/pyproject.toml ingestion/benchmarks/uv.lock ./
RUN uv sync --locked --no-cache --only-group proxy
ENV PATH="/benchmark/.venv/bin:$PATH"

# Generate the proxy's gRPC stubs from the shared proto. They are not checked in.
COPY proto/auth.proto /proto/auth.proto
RUN python -m grpc_tools.protoc \
    -I /proto \
    --python_out=. \
    --grpc_python_out=. \
    /proto/auth.proto

COPY ingestion/benchmarks/auth_backend_proxy.py ./

# gRPC proxy (internal Docker network only)
EXPOSE 50054
# Control API: health, stats, reset, and mode (published by Compose)
EXPOSE 50055

ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["python", "/benchmark/auth_backend_proxy.py"]

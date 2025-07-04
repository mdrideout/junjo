# =================================================================
# STAGE 1: Builder
# We use an official Go image. This is simple, reliable, and
# contains all necessary build tools.
# =================================================================
FROM golang:1.24-bookworm AS builder

# This build stage is where we compile the application.
# It contains the Go toolchain and C compilers (build-essential).

WORKDIR /app

# 1. Optimize Docker's layer cache for Go modules.
#    This step only re-runs if your dependencies change.
COPY go.mod go.sum ./
RUN go mod download

# 2. Copy the rest of your application's source code.
COPY . .

# 3. Build the application binary.
#    - TARGETARCH is an automatic build argument from Docker Buildx. It
#      makes your build portable across architectures (e.g., amd64, arm64).
#    - CGO_ENABLED=1 is set here, accommodating your need for DuckDB.
#    - -ldflags "-w -s" strips debug symbols, creating a smaller binary.
ARG TARGETARCH
RUN CGO_ENABLED=1 GOOS=linux GOARCH=${TARGETARCH} go build -ldflags="-w -s" -v -o /server .


# =================================================================
# STAGE 2: Production (The default final stage)
# Builds a minimal, secure image for deployment.
# It starts from a clean Debian base, NOT from the builder.
# =================================================================
FROM debian:bookworm-slim AS production

# Add curl to enable healthcheck
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Set a label to identify the image stage, useful for diagnostics.
LABEL stage=production

# Copy essential runtime files from the 'builder' stage.
# ca-certificates are necessary for your app to make secure HTTPS calls.
COPY --from=builder /etc/ssl/certs/ca-certificates.crt /etc/ssl/certs/

# Create a dedicated, non-root user for security. This is a critical
# best practice to limit the blast radius of any potential vulnerability.
RUN groupadd --system app && useradd --system --gid app app
USER app

# Copy ONLY the compiled binary from the 'builder' stage.
# The final image will NOT contain source code or build tools.
COPY --from=builder /server /server

# Expose the application ports.
EXPOSE 1323
EXPOSE 50051

# Set the command to run your application.
CMD ["/server"]


# =================================================================
# STAGE 3: Development
# Builds an image for local development with hot-reloading.
# =================================================================
FROM golang:1.24-bookworm AS development

# Set a label for diagnostics.
LABEL stage=development

WORKDIR /app

# As before, cache module downloads.
COPY go.mod go.sum ./
RUN go mod download

# Install 'air' for hot-reloading.
RUN go install github.com/air-verse/air@latest

# Copy the source code for 'air' to watch.
COPY . .

# Expose ports needed for development.
EXPOSE 1323
EXPOSE 50051

# The command to run the hot-reloader. Air will re-compile and re-run
# your app inside the container whenever you save a file on your host machine.
CMD ["air"]
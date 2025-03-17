# Base Stage (for both production and development)
FROM debian:bookworm-slim AS base

# Install Go (and build-essential for CGO, even if disabled later)
ARG GO_VERSION=1.24.1
ARG GO_ARCH=arm64
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        build-essential \
        ca-certificates \
        wget \
        unzip \
    && wget -q https://dl.google.com/go/go${GO_VERSION}.linux-${GO_ARCH}.tar.gz -O /tmp/go${GO_VERSION}.linux-${GO_ARCH}.tar.gz && \
    tar -C /usr/local -xzf /tmp/go${GO_VERSION}.linux-${GO_ARCH}.tar.gz && \
    rm /tmp/go${GO_VERSION}.linux-${GO_ARCH}.tar.gz && \
    rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

# Set GOPATH and PATH (important for Go tools)
ENV GOPATH=/go
ENV PATH=$GOPATH/bin:/usr/local/go/bin:$PATH

WORKDIR /app

COPY go.mod go.sum ./
RUN go mod download

COPY . .



# ================================================
# Production Stage
# TODO: Optimize builders so that we use optimized debian-slim here, but build with full go:debian image
FROM base AS production

RUN CGO_ENABLED=0 GOOS=linux go build -mod=readonly -v -o server

EXPOSE 1323

CMD ["./server"]


# ================================================
# Development Stage
FROM base AS development

# Install air for hot reloading
# Explicitly enable CGO and set GOARCH for the air installation.
ENV CGO_ENABLED=1
ENV GOARCH=arm64
RUN go install github.com/air-verse/air@latest

WORKDIR /app-dev

CMD ["air"] 
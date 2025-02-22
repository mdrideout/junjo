# Base Stage (for both production and development)
FROM golang:1.24-alpine AS base

WORKDIR /app

COPY go.mod go.sum ./
RUN go mod download

COPY . .

# ================================================
# Production Stage
FROM base AS production

RUN CGO_ENABLED=0 GOOS=linux go build -mod=readonly -v -o server

EXPOSE 1323

CMD ["./server"]


# ================================================
# Development Stage
FROM base AS development

# Install air for hot reloading
RUN go install github.com/air-verse/air@latest

WORKDIR /app-dev

CMD ["air"] 
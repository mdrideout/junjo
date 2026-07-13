FROM caddy:2-builder-alpine AS builder

RUN xcaddy build \
  --with github.com/caddy-dns/cloudflare

FROM caddy:2-alpine

LABEL org.opencontainers.image.source="https://github.com/mdrideout/junjo" \
      org.opencontainers.image.licenses="Apache-2.0"

COPY --from=builder /usr/bin/caddy /usr/bin/caddy

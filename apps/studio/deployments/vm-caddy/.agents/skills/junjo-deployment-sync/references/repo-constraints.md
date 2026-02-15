# Deployment-Example Constraints

## Repository purpose

This repository is an opinionated production VM deployment example for Junjo AI Studio.
It intentionally includes:

- `caddy/` reverse proxy example and Cloudflare DNS challenge flow.
- `junjo_app/` demo application that continuously emits telemetry.
- Junjo core services (backend/ingestion/frontend) as prebuilt Docker images.

## Non-negotiable guardrails

- Do not add `JUNJO_BUILD_TARGET` to this repository.
- Do not remove `caddy` or `junjo-app` services from `docker-compose.yml`.
- Keep Caddy/Cloudflare production setup documented.
- Keep manual `.env` setup documented even when script setup exists.
- Keep `scripts/junjo` focused on `.env` management; do not silently edit `caddy/Caddyfile`.

## Files that typically change during release sync

- `docker-compose.yml`
  - Junjo image tags
  - Backend memory/DataFusion passthrough vars
  - Keep deployment-example-specific services
- `.env.example`
  - New backend tuning vars
  - Cloudflare token + staging notes
- `scripts/junjo`
  - Setup UX and env write behavior
  - Production URL derivation
  - Cloudflare token handling
- `README.md`
  - Quick Start and production setup consistency
  - Cloudflare token requirements
  - Image version references

## Recommended validation commands

```bash
python3 -m py_compile scripts/junjo
./scripts/junjo setup --dry-run --non-interactive --env development
./scripts/junjo setup --dry-run --non-interactive --env production --hostname junjo.example.com --cloudflare-token test_token
docker compose --env-file .env.example config
```

## Release sync reporting checklist

- Confirm upstream release date/tag and changelog scope.
- List intentional diffs from upstream/minimal-build due to this repo purpose.
- Confirm `CLOUDFLARE_API_TOKEN` handling in both docs and setup script.
- Confirm no accidental regressions in `caddy/Caddyfile` instructions.

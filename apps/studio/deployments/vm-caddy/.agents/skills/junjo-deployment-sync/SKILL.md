---
name: junjo-deployment-sync
description: Investigate upstream Junjo AI Studio releases and apply aligned updates to the junjo-ai-studio-deployment-example repository. Use when asked to sync this repo with mdrideout/junjo-ai-studio or mdrideout/junjo-ai-studio-minimal-build, bump release tags, update docker-compose/.env/setup docs, or validate migration readiness while preserving deployment-example constraints (prebuilt Junjo images, no JUNJO_BUILD_TARGET, and included Caddy plus junjo-app services).
---

# Junjo Deployment Sync

Use this skill to perform repeatable release-sync updates for this deployment example repository.

## Workflow

1. Run the release audit helper:
   - `./.agents/skills/junjo-deployment-sync/scripts/release_audit.sh <target-tag>`
   - If `<target-tag>` is omitted, the script resolves the latest upstream release tag.
2. Read `references/repo-constraints.md` before editing.
3. Compare upstream and minimal-build deltas for these files first:
   - `docker-compose.yml`
   - `.env.example`
   - `scripts/junjo`
   - `README.md`
4. Apply updates in this repository while preserving deployment-example-specific behavior.
5. Run validations and report outcomes, including any intentionally preserved differences.

## Update Rules

### Compose and Runtime
- Bump Junjo core images to the target release in `docker-compose.yml`.
- Keep `caddy` and `junjo-app` services in place.
- Keep this repository in prebuilt-image mode for Junjo core services.
- Do not introduce `JUNJO_BUILD_TARGET`.
- Wire backend memory/DataFusion passthrough env vars if present upstream/minimal-build.

### Environment Template
- Ensure `.env.example` exposes required tuning variables used by compose.
- Keep production URL placeholders compatible with setup automation.
- Keep Caddy/Cloudflare variables documented for this deployment example.

### Setup Script
- Keep `scripts/junjo` focused on `.env` generation/update.
- Support production hostname-derived URLs.
- Support Cloudflare token setup for production (`CLOUDFLARE_API_TOKEN`).
- Preserve safe backup behavior (`<env-file>.bak` only when target exists).

### Documentation
- Keep Quick Start concise.
- Present script setup as convenience and retain manual setup steps.
- Explicitly state Cloudflare token requirement for production Caddy SSL/DNS challenge.

## Validation

Run this validation sequence after edits:

```bash
python3 -m py_compile scripts/junjo
./scripts/junjo setup --dry-run --non-interactive --env development
./scripts/junjo setup --dry-run --non-interactive --env production --hostname junjo.example.com --cloudflare-token test_token
docker compose --env-file .env.example config
```

Also verify:
- No unintended introduction of `JUNJO_BUILD_TARGET` in this repo.
- `docker-compose.yml` still includes both `caddy` and `junjo-app`.
- README and script behavior stay consistent.

## Resources
- `scripts/release_audit.sh`: Pull upstream references and print release-oriented deltas.
- `references/repo-constraints.md`: Hard constraints and file-specific guardrails for this repository.

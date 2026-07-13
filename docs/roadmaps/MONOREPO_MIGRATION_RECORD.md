# Junjo monorepo migration record

## Scope

This record accompanies ADR 0001 and the migration plan. It records the local
source migration. GitHub issues, repository archival, secrets, environments,
branch protection, and trusted-publisher configuration are operator cutover
work and cannot be completed by repository commits.

## Source revisions

- destination Junjo planning tip: `371845168dc1aaf94ef2bf54c590ae0c2cad9e29`
- source Studio `master`: `ccb0031156d077aa4c5264290df15cc22a8f5d46`
- rewritten Studio `master`: `54bde3c8f5a762cf802323f8c2a94b030ddbdc4f`
- source Studio tree: `26761a0f0665a9c62d77fb2f11a15278007950df`
- imported `apps/studio` tree: `26761a0f0665a9c62d77fb2f11a15278007950df`
- Studio tracked files at the source and imported tip: 363
- Studio commits reachable from `master` at the source and imported tip: 372

The source and imported tree identities match. `git log --follow` from an
`apps/studio` file reaches its original Studio commits.

## Rehearsed and executed history import

The import was first run end-to-end in disposable clones. The real import used
the same sequence, with a temporary local remote removed after the merge:

```bash
git clone --no-local ../junjo-ai-studio "$TMP_IMPORT/studio-filtered"
git -C "$TMP_IMPORT/studio-filtered" filter-repo \
  --to-subdirectory-filter apps/studio \
  --tag-rename '':'studio-' \
  --force

git remote add studio-import "$TMP_IMPORT/studio-filtered"
git fetch studio-import master --tags
git merge --allow-unrelated-histories --no-ff --no-edit studio-import/master
git remote remove studio-import
```

Before publication, each temporary `studio-<version>` tag was renamed without
moving its target to the accepted `studio-v<version>` namespace.

The import intentionally includes Studio `master` ancestry and release tags.
Unmerged historical branch tips (`multi-app-bug`, `nov-2025-improvements`, and
`oct-2025-improvements`) remain in the archived source repository. The imported
history includes historical binaries and produces an approximately 135 MiB Git
pack; that provenance and repository-size cost is accepted.

## Local data protection

Only Git-tracked files were moved or imported. Existing ignored SDK example
virtual environments, `node_modules`, databases, logs, generated docs, Studio
data, and build caches were not imported or deleted.

## Validation results

The migrated tree passed the repository-owned validation gates on 2026-07-12:

- platform structure and release-routing invariant script passed;
- canonical telemetry contract version 1 validated six Workflow fixtures,
  including JSON Schema validation of their envelopes and graph snapshots;
- Python SDK: 99 tests, Ruff, ty, Sphinx with no warnings, package build, and
  Twine validation passed;
- the migrated Python wheel has the same 21-file inventory and top-level import
  package as the pre-migration wheel, and a clean-environment installed-wheel
  Workflow smoke test passed;
- Studio version synchronization passed at 0.81.1;
- Studio backend: 47 unit, 53 integration, and 8 gRPC tests passed, with three
  optional integration skips;
- Studio ingestion: 7 unit and 14 integration tests passed, and locked Cargo
  check passed;
- Studio frontend: 125 tests passed, ESLint completed with zero findings, and
  the TypeScript/Vite production build passed;
- REST API contract generation and validation passed;
- protobuf regeneration produced no tracked diff using system protoc 30.2 and
  the locked Python generator;
- development/production Compose configuration rendered successfully;
- backend, frontend, and ingestion production Docker images built from
  `apps/studio` as their context;
- Gitleaks scanned the combined committed histories with no leaks after four
  historical documentation false positives were fingerprint-scoped in
  `.gitleaksignore`.

Non-blocking baseline observations: npm reports 28 dependency advisories, the
frontend production build reports a large-chunk advisory, and backend tests
report upstream HTTPX per-request-cookie deprecation warnings. None were
introduced by the path migration; they remain explicit follow-up maintenance.

## Operator cutover checklist

- [ ] Configure required checks and branch protection in the destination.
- [ ] Recreate Studio publishing secrets and environments in the destination.
- [ ] Confirm the PyPI trusted publisher accepts the moved workflow.
- [ ] Confirm Docker Hub credentials and image permissions.
- [ ] Migrate or close active Studio issues and roadmap items.
- [ ] Publish an archive notice in `junjo-ai-studio` pointing here.
- [ ] Disable Studio workflows and releases in the archived repository.
- [ ] Push the intentionally namespaced `studio-v*` historical tags.
- [ ] Perform release dry runs before enabling production publishing.

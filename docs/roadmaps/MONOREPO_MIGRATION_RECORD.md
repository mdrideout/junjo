# Junjo monorepo migration record

## Status

This record proves the completed source consolidation for the Python SDK,
Studio, website, minimal Studio distribution, and VM/Caddy distribution. It
also records the repository implementation for Apache-2.0 licensing,
deterministic distribution exports, path-owned CI, and the protected Studio
release DAG.

Production mirror publication, hosting cutover, environment credentials,
trusted-publisher changes, branch-protection changes, and source-repository
retirement remain operator cutover work. This record does not claim those
external mutations have happened.

GitHub Actions, environments, credentials, trusted publishing, Cloudflare,
mirror, archival, verification, and rollback steps follow
`MONOREPO_GITHUB_CUTOVER_RUNBOOK.md`.

Append external settings evidence and production verification here as the
operator cutover runs. Do not convert planned work into recorded fact before it
passes its validation gates.

## Scope

This record accompanies ADR 0001 and the migration plan. The evidence below
records the local source migrations and repository implementation. GitHub issues,
repository archival, distribution-mirror settings, website hosting, secrets,
environments, branch protection, and trusted-publisher configuration are
operator cutover work and cannot be completed by repository commits.

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

### Expanded source revisions

| Component | Prepared source revision | Rewritten import revision | Destination merge | Source/imported subtree | Tracked files | Reachable commits |
| --- | --- | --- | --- | --- | ---: | ---: |
| Minimal distribution | `631319feaa4c918e919460370ca51862e7774d87` | `981dcd327ae2b09fb31ed1598af76d651da3ba9b` | `dbef8621347f909d7acbb85a320c26fa8e05c18c` | `11b30f46f48a1315b0933c0d502a15a0432947a4` | 6 | 22 |
| VM/Caddy distribution | `099e07f45d4b238f6aba63736a2bd8b1f37501e5` | `7baec1c12d07cfaf99367fc943ab16798ff397d6` | `c0ec2c34ffd6f374fe3a75d2a2adfd9f073410cd` | `58ef4217cd158c3a284769c96430a50a7dd653ea` | 16 | 58 |
| Website | `9964091f3c77fdbe49b2bc0f4b13450b417b5cb2` | `49a87bc320b036e0723643a765380fdcf4f3bde6` | `df119c0aebaf212c35ef08538c29daf674e677e9` | `5133752d25b7292dbf3aa53201b2eed3d8fac5af` | 17 | 5 |

Each prepared source tree is byte-identical to its corresponding imported
destination subtree at the merge commit. Source preparation was committed and
pushed on `codex/monorepo-source-prep` in each source repository before history
rewriting. The website preparation commit intentionally included the existing
website redesign; an unrelated untracked local `.agents` bundle was not
imported.

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

The three expanded imports used the same history-preserving pattern with these
destination filters:

```bash
git filter-repo --to-subdirectory-filter apps/studio/deployments/minimal --force
git filter-repo --to-subdirectory-filter apps/studio/deployments/vm-caddy --force
git filter-repo --to-subdirectory-filter apps/website --force
```

Minimal historical tags were namespaced as `studio-minimal-v*`; VM/Caddy tags
were namespaced as `studio-deployment-v*`. Four tags exist in each namespace.
The website had no release-tag stream to import. New distribution versions are
released only by `studio-v*`; the two imported namespaces are historical.

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

The expanded repository implementation also passed these gates on 2026-07-12:

- every Junjo-authored component and standalone distribution contains the same
  complete Apache License 2.0 text;
- `.env.bak` is explicitly ignored by Studio and both standalone distribution
  roots, is untracked, and is rejected from exports;
- website locked install, Astro checks, production build, and production npm
  audit passed with zero audit findings;
- 36 offline platform-tooling tests passed, including CI path routing,
  exact Compose contracts, deterministic Git-revision exports, secret/runtime
  exclusion, license equality, archive reproducibility, mirror authentication,
  file content/mode verification, release-evidence reconstruction, and
  publication idempotence;
- both canonical deployment distributions passed full Compose and setup-wizard
  validation for Studio 0.81.1;
- Actionlint 1.7.12 passed every workflow;
- Zizmor 1.26.1 reported no workflow security findings;
- every external GitHub Action reference is pinned to an immutable commit;
- the platform repository invariant and telemetry-contract validators passed.

Non-blocking baseline observations: Studio npm reports 28 dependency
advisories, including 11 production advisories; the frontend production build
reports a large-chunk advisory; backend tests report 18 upstream HTTPX
per-request-cookie deprecation warnings; Rustfmt reports existing formatting in
`ingestion/src/wal/span_record.rs`; and Clippy reports six existing warnings.
The repository's existing Studio CI does not gate Rustfmt or Clippy. None were
introduced by the structural migration; they remain explicit follow-up
maintenance.

## Repository migration work

- [x] Complete the expanded website and deployment source imports.
- [x] Replace all Junjo-owned AGPL declarations with Apache-2.0 and validate
  every independently packaged or exported component.
- [x] Add and validate `.env.bak` ignores for Studio and both deployment
  distributions.
- [x] Add website, deployment, license, archive, and mirror validation in the
  monorepo.
- [x] Append exact source revisions, import commands, tree identities, and
  validation results to this record.

## Operator cutover checklist

- [ ] Update surviving distribution and archived source repository default
  branches so they do not advertise a conflicting current license.
- [ ] Configure one-way publication credentials for both deployment mirrors.
- [ ] Convert `junjo-ai-studio-minimal-build` into a generated distribution
  whose canonical source is `apps/studio/deployments/minimal`.
- [ ] Convert `junjo-ai-studio-deployment-example` into a generated
  distribution whose canonical source is
  `apps/studio/deployments/vm-caddy`.
- [ ] Cut website hosting over to `apps/website`, then archive the old website
  source repository with a destination notice.
- [ ] Configure required checks and branch protection in the destination.
- [ ] Recreate Studio publishing secrets and environments in the destination.
- [ ] Confirm the PyPI trusted publisher accepts the moved workflow.
- [ ] Confirm Docker Hub credentials and image permissions.
- [ ] Migrate or close active Studio issues and roadmap items.
- [ ] Publish an archive notice in `junjo-ai-studio` pointing here.
- [ ] Disable Studio workflows and releases in the archived repository.
- [x] Push the intentionally namespaced `studio-v*` historical tags.
- [ ] Perform release dry runs before enabling production publishing.

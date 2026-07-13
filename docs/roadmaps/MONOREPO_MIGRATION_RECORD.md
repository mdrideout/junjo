# Junjo monorepo migration record

## Status

This record proves the completed source imports and records local repository
remediation evidence for
the Python SDK, Studio, website, minimal Studio distribution, and VM/Caddy
distribution. The fixes required by
`MONOREPO_MIGRATION_REMEDIATION_PLAN.md` were merged by pull request 12 as merge
commit `02f34073ceb40963e716498cf2caaaddafa2db28` on 2026-07-13.

Production cutover is not complete. Credentials, trusted publishing, direct
hosting cutover, first production releases, and old-repository retirement
remain operator work. Historical Catalyst rights are resolved by the license
holder confirmation recorded below.

Production mirror publication, hosting cutover, environment credentials,
trusted-publisher changes, action-SHA enforcement, the immutable release-tag
ruleset, and source-repository retirement remain operator cutover work. This
record does not claim those external mutations have happened.

GitHub Actions, environments, credentials, trusted publishing, Cloudflare,
mirror, archival, verification, and forward-recovery steps follow
`MONOREPO_GITHUB_CUTOVER_RUNBOOK.md`.

Append external settings evidence and production verification here as the
operator cutover runs. Do not convert planned work into recorded fact before it
passes its validation gates.

## Scope

This record accompanies ADR 0001 and the migration plan. The evidence below
records the local source migrations and repository implementation. GitHub issues,
repository archival, distribution-mirror settings, website hosting, secrets,
environment policies, repository protections, and trusted-publisher
configuration require operator evidence and cannot be completed by repository
commits alone.

## Destination control-plane snapshot

Verified through the GitHub API on 2026-07-13:

- `master` protection is strict, enforced for administrators, requires resolved
  conversations, and requires `required` plus `Gitleaks Scan`;
- `pypi` allows only `sdk-python-v*` tags;
- `studio-dockerhub-production`, `studio-distributions-production`, and
  `studio-release-production` allow only `studio-v*` tags;
- the four environments contain no stored secrets;
- `studio-dockerhub-production` does not yet contain the exclusive-authority
  confirmation;
- publication destinations are repository-owned in
  `tooling/studio_release_contract.json`; obsolete mutable mirror-name
  repository variables were removed;
- repository Actions remain enabled for all actions and repository-level SHA
  pin enforcement remains disabled until the final workflow set is merged.

The environments and policies existing is not publishing proof. Docker Hub,
GitHub App, and PyPI authorities remain incomplete until their credential or
trusted-publisher gates are exercised successfully.

The public Docker Hub API reported `enabled: false` with retained rule `.*` for
all three Studio repositories on 2026-07-13. The implemented production
workflow will fail before registry mutation until Gate B installs the two exact
contract rules and records this monorepo as the exclusive publisher.

The operator accepted the existing `mdrideout` personal Docker Hub namespace as
the permanent image namespace. No organization, repository rename, image copy,
or parallel image path is part of the cutover. On 2026-07-13 the public Docker
Hub API also reported `is_automated: false` for the backend, frontend, and
ingestion repositories; Docker Hub Autobuild disablement is therefore complete.

## Final pull-request and merge evidence

Pull request 12 merged with history preserved:

- final pull-request head:
  `3f8e5b32f52257e62044f178d197c359974407e8`;
- final Platform Gate run
  `https://github.com/mdrideout/junjo/actions/runs/29264365485` passed every
  routed component, both-architecture dry build, release rehearsal, and local
  telemetry smoke;
- final Gitleaks run
  `https://github.com/mdrideout/junjo/actions/runs/29264364485` passed;
- pull request 12 merged at
  `02f34073ceb40963e716498cf2caaaddafa2db28` on 2026-07-13;
- every component workflow triggered on that `master` merge commit completed
  successfully, including deployment validation run
  `https://github.com/mdrideout/junjo/actions/runs/29269170458` and Gitleaks run
  `https://github.com/mdrideout/junjo/actions/runs/29269171102`;
- the only non-green check is the legacy Cloudflare Pages integration using
  obsolete pre-monorepo build settings. Production downtime and preview
  continuity are not migration requirements, so that check is intentionally
  non-blocking and Cloudflare is reconfigured after merge.

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
Unmerged historical branch tips (`multi-app-bug`, `nov-2025-improvements`,
`oct-2025-improvements`, and `feat/node-exceptions-dashboard`) remain in the
source repository. The last branch is at
`6d3171c1c41270ad5baa92ad361179bf60942118`, three commits ahead of its base. It
is unfinished work and is not canonical monorepo source; retain it as readable
archive history. Destination [issue 13](https://github.com/mdrideout/junjo/issues/13)
records the explicit review boundary for any desired product work.
The imported history includes historical binaries and produces an
approximately 135 MiB Git pack; that provenance and repository-size cost is
accepted.

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

## Historical Catalyst decision

On 2026-07-13, the license holder confirmed that Tailwind UI/Plus was
legitimately purchased and used for the Junjo AI Studio application end
product. ADR 0002 therefore accepts preservation of the imported Studio commits
and tags under the Tailwind Plus terms and the repository licenses present in
their historical snapshots. The historical distribution-rights gate is closed;
no history rewrite is required.

The current Junjo UI implementation remains independently authored. Current
source and artifacts contain no Catalyst component tree, compatibility layer,
or fallback. New shared UI foundations must use Base UI, native platform
behavior, or similarly permissively licensed open-source primitives behind
Junjo-owned semantic component contracts.

## Local data protection

Only Git-tracked files were moved or imported. Existing ignored SDK example
virtual environments, `node_modules`, databases, logs, generated docs, Studio
data, and build caches were not imported or deleted.

## Validation results

The following repository-owned validations ran successfully on 2026-07-12:

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
- Gitleaks scanned the combined committed histories with no leaks. Broad path
  and regex allowlists were subsequently removed; unavoidable historical
  findings are fingerprint-scoped in `.gitleaksignore`.

The expanded repository implementation also passed these existing checks on
2026-07-12. Review subsequently found that their coverage is not sufficient to
establish migration completion:

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
- both canonical deployment distributions passed Compose rendering and the
  existing limited setup-script checks for Studio 0.81.1; these checks do not
  yet prove development/production generation, secret handling, reruns,
  backups, VM image builds, or end-to-end telemetry;
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

## Remediation implementation and validation

The remediation work ran successfully on 2026-07-13 against the current
worktree prepared for pull request 12. These are local results, not a substitute
for the final pushed-revision checks:

- ADR 0002 and Studio ADRs 005 and 006 are accepted and match the current
  implementation. The release destinations and immutable `0.81.1` baseline are
  fixed in `tooling/studio_release_contract.json`, together with the exact
  Docker Hub rules that protect stable versions and full source revisions; the
  synchronized candidate version is `0.81.2`.
- The nine-file Catalyst tree was deleted. Current frontend source has no
  Catalyst or Headless UI implementation, no compatibility component surface,
  and no direct `@headlessui/react`, `framer-motion`,
  `@radix-ui/react-switch`, or `radix-ui` dependency. Studio's Junjo-owned
  action, modal, switch, link, and application-shell contracts encapsulate Base
  UI 1.6.0, and `THIRD_PARTY_NOTICES.md` records the Base UI and Tailwind CSS
  MIT notices plus resolved historical Catalyst provenance.
- A clean production build of pre-remediation revision `6341a60` contained
  20,896 KiB across 95 output files, with a 2,653,229-byte main JavaScript chunk
  and 99,137-byte main stylesheet. The final replacement build contains 4,648
  KiB across 50 output files, with a 2,526,072-byte main JavaScript chunk and
  65,531-byte main stylesheet. The replacement therefore reduced the served
  build by 16,248 KiB, the main JavaScript chunk by 127,157 bytes, and the main
  stylesheet by 33,606 bytes. The 45 removed files were production source maps;
  the artifact validator proves no map or map reference is shipped.
- The lock-bound artifact inventories record 277 production frontend packages
  and 191 normal Rust dependencies across Linux AMD64/ARM64. Fast validation,
  exact Cargo-metadata regeneration, installed frontend override evidence, and
  production image copy contracts passed. All three images carry Junjo's
  license and Studio notice; the frontend/ingestion images carry their
  inventories and the backend carries its production lock. The first-image
  technical artifact-license review completed on 2026-07-13: every dependency
  has an accepted expression, the sole frontend metadata override is bound to
  the exact Khroma registry license file, and no unknown license remains. The
  decision approves these dependency closures and notices for the first Studio
  release; exact registry digests remain subject to Gate C verification. This
  technical record is not legal advice. Inspection of the final local
  Linux/ARM64 images found image IDs
  `3deec967201f9928b3518f4a0920df1d56f054e348d9ab85616da61e3358db2d`
  (backend),
  `f6c128acbb491d786784bd4fdc268d8d2505342a64437993692e6015dd6f6a32`
  (frontend), and
  `2166260c41417edf6e2db0e9ec5c2d377e3032aa189723f1b3da1abac7067c82`
  (ingestion). Their common license hash is
  `cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30`,
  the common notice at
  `e7879d9e3717ffa1f8699d93aaa4e9041da0003871af664a10e5810b2ee93462`,
  and component evidence hashes `095499e643cb88caee1ebef99e81e859b71cc77367357032e4d3fb1204d8912a`
  (backend), `f7145b5efff0ef63b18589f09d6438882541782577997d1dc44ff231e88abcdf`
  (frontend), and
  `e4c5bcbddd6489f11d263660aa77136506d8500888d561f547a901fccf287341`
  (ingestion).
- `python3 -m unittest discover -s tooling/tests -v` passed all 108 tests. The
  suite covers CI routing, strict release admission and evidence, exact mirror
  identity and all-destination preflight, live Docker Hub control validation,
  failed-job artifact retries, archive/export behavior, all three setup wizards, secret
  redaction, atomic `0600` environment/backup publication,
  ignored interruption residue, reruns/backups/rotation, artifact-license
  closure, digest-only registry smoke, Compose contracts, and failure cleanup.
- `python3 tooling/scripts/validate_repository.py` and
  `python3 contracts/telemetry/compatibility/validate_contract.py` passed.
- strict Gitleaks 8.30.0 scans passed for the entire reachable history and for a
  temporary copy containing every existing tracked or untracked, non-ignored
  current-tree file. The configuration has no path or regular-expression
  allowlist; unavoidable history findings are exact fingerprints. A temporary
  high-entropy GitHub-token-shaped file was then rejected as the negative
  control.
- Actionlint 1.7.12 passed every workflow. Zizmor 1.26.1 reported no workflow
  findings.
- `apps/studio/run-all-tests.sh` passed at `0.81.2`: 47 backend unit tests, 53
  backend integration tests with three optional skips, eight gRPC tests, seven
  ingestion unit tests, 14 ingestion integration tests, 138 frontend tests,
  ESLint, the production TypeScript/Vite build, 17 REST contract tests, and
  protobuf reproducibility.
- The deployment validator rendered both `0.81.2` distributions. The exact
  local Linux/AMD64 smoke built backend, frontend, ingestion, Caddy, and the VM
  example application; created the first Studio user and API key; ran the real
  example workflow; and proved that the workflow was queryable through Studio.
  It then removed its containers, volumes, network, and temporary distribution
  images.
- The separate root-runtime validator rendered development and production for
  both base Compose and the monitoring overlay, then checked exact source build
  targets, internal service wiring, mounts, project-scoped volumes/networks,
  and the cAdvisor boundary without building, pulling, or starting containers.
- The Python SDK passed Ruff, 99 tests, `ty` with warnings treated as errors,
  warning-free Sphinx HTML, wheel and source builds, and Twine validation. Both
  artifacts contain the Apache license metadata.
- The website passed locked installation, Astro checks across six source files
  with zero findings, a five-route static production build, deterministic
  validation of all seven generated HTML files and their internal references,
  the obsolete-source URL guard, and a production dependency audit with zero
  vulnerabilities.
- `git diff --check` passed.

No production authority was used by these validations. Protected-environment
credentials, old-publisher disablement, live Docker Hub
immutable-rule configuration, exclusive-authority confirmation, and first
production releases remain cutover evidence and are not claimed here.

## Repository migration work

- [x] Complete the expanded website and deployment source imports.
- [x] Replace all Junjo-owned AGPL declarations with Apache-2.0 and validate
  every independently packaged or exported component.
- [x] Add and validate `.env`, `.env.bak`, and private staging-file ignores for
  Studio and both deployment distributions.
- [x] Add website, deployment, license, archive, and mirror validation in the
  monorepo.
- [x] Append exact source revisions, import commands, tree identities, and
  validation results to this record.
- [x] Replace the current Catalyst implementation with the Junjo-owned Base UI
  foundation and preserve third-party notices.
- [x] Implement the globally serialized, forward-only Studio release
  transaction and exact image/distribution evidence contracts.
- [x] Add complete setup-wizard tests and a real end-to-end Studio telemetry
  smoke at version 0.81.2.
- [x] Close CI-routing, current-tree secret scanning, package metadata, OCI
  metadata, and repository-invariant gaps.

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
- [x] Configure required checks and branch protection in the destination.
- [x] Create tag-restricted publishing environments in the destination.
- [ ] Recreate or rotate the approved Studio publishing credentials in their
  owning environments.
- [ ] Confirm the PyPI trusted publisher accepts the moved workflow.
- [ ] Confirm Docker Hub credentials and image permissions.
- [x] Confirm Docker Hub Autobuilds are disabled on all three image
  repositories.
- [ ] Disable the old Studio publisher, configure the exact immutable-tag rules
  on all three existing `mdrideout` image repositories, and then set
  `STUDIO_RELEASE_AUTHORITY_CUTOVER=mdrideout/junjo` in the protected Docker Hub
  environment.
- [ ] Migrate or close active Studio issues and roadmap items.
- [ ] Publish an archive notice in `junjo-ai-studio` pointing here.
- [ ] Disable all remaining Studio workflows before archiving the old repository.
- [x] Push the intentionally namespaced `studio-v*` historical tags.
- [ ] Perform release dry runs before enabling production publishing.

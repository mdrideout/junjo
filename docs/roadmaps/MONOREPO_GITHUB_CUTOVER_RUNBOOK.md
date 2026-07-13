# Junjo Monorepo GitHub And Hosting Cutover Runbook

## Status

Approved implementation runbook.

This document turns Phases 6 through 8 of `MONOREPO_MIGRATION_PLAN.md` into an
executable repository and operator cutover. It covers GitHub Actions, required
checks, environments, credentials, PyPI trusted publishing, Docker Hub,
deployment-distribution mirrors, Cloudflare Pages, old-repository shutdown,
verification, and rollback.

Do not treat a checked box as evidence by itself. Record the exact workflow run,
deployment, release, commit, image digest, or settings snapshot in
`MONOREPO_MIGRATION_RECORD.md`.

## Safety Rules

- Never print, copy into documentation, or commit a secret value.
- Inventory secret names only. GitHub does not expose stored values.
- Recreate or rotate credentials in their final environment; do not attempt to
  copy repository secrets through logs or temporary files.
- Pull-request workflows are deterministic and secretless.
- Never use `pull_request_target` for code validation or deployment.
- Production credentials are available only to jobs referencing their owning
  protected environment.
- Give every workflow `permissions: contents: read` by default and elevate only
  the job that needs additional access.
- Do not archive or disconnect a working source/deployment until the replacement
  has passed its production verification gate.
- Do not move or delete an immutable package or image version during rollback.
  Recover with a forward fix or corrective release.
- Do not force-push generated distribution history during ordinary publication.

## Current Control-Plane Inventory

Snapshot date: 2026-07-12.

### Destination repository

`mdrideout/junjo` currently has:

- public visibility and `master` as the default branch;
- no repository Actions secrets;
- no repository Actions variables;
- one environment named `pypi` with no protection rules or branch/tag policy;
- read-only default `GITHUB_TOKEN` permissions;
- all GitHub Actions allowed and no repository-level SHA-pin requirement;
- strict `master` protection with administrator enforcement and conversation
  resolution;
- required checks named `library-health` and `Gitleaks Scan`;
- no repository rulesets.

The migration branch contains the new monorepo workflows, but they are not
active as default-branch workflows until merged.

### Old Studio repository

`mdrideout/junjo-ai-studio` currently remains public, unarchived, and able to
run active workflows. Its secret names are:

- `DOCKERHUB_USERNAME`
- `DOCKERHUB_TOKEN`
- `OPENAI_API_KEY`
- `ANTHROPIC_API_KEY`
- `GEMINI_API_KEY`
- `JUNJO_SESSION_SECRET`
- `JUNJO_SECURE_COOKIE_KEY`

Secret values are not readable and are not migration inputs. The final plan
does not recreate all seven in the destination.

### Website and distribution repositories

- `mdrideout/junjo-website` is private and has no Actions secrets, workflows,
  environments, or GitHub Pages configuration.
- `mdrideout/junjo-ai-studio-minimal-build` is public and configured as a
  GitHub template. It has no Actions secrets or workflows.
- `mdrideout/junjo-ai-studio-deployment-example` is public and is not currently
  configured as a GitHub template. It has no Actions secrets or workflows.

### Cloudflare Pages

Two Cloudflare Pages Git integrations must survive the source moves:

- `junjo-python-api` currently builds Python API documentation from
  `mdrideout/junjo`;
- `junjo-website` currently builds `junjo.ai` from
  `mdrideout/junjo-website`.

The source repository, root directory, output directory, and build-watch paths
must be updated for the monorepo. GitHub Pages is not the deployment target.

## Target GitHub Environments

### `pypi`

Purpose: publish the Python SDK through PyPI Trusted Publishing.

- Stored secrets: none.
- Required workflow permission: `id-token: write` on the publish job only.
- Allowed ref: `sdk-python-v*` tags.
- PyPI publisher identity:
  - owner: `mdrideout`
  - repository: `junjo`
  - workflow filename: `python-publish.yml`
  - environment: `pypi`

The old trusted-publisher workflow filename was `publish.yml`. Update the PyPI
publisher before the next package release.

### `studio-dockerhub-production`

Purpose: publish Studio images, manifests, and Docker Hub descriptions.

- Environment secrets:
  - `DOCKERHUB_USERNAME`
  - `DOCKERHUB_TOKEN`
- Allowed ref: `studio-v*` tags.
- Jobs: image architecture push, manifest creation/promotion, and Docker Hub
  description update only.

Create a new least-privilege Docker Hub token rather than reusing an unknown
repository-secret value when possible.

### `studio-distributions-production`

Purpose: publish the minimal and VM/Caddy distributions to their standalone
repositories.

Preferred authentication is a GitHub App installed only on:

- `mdrideout/junjo-ai-studio-minimal-build`
- `mdrideout/junjo-ai-studio-deployment-example`

The App receives repository contents write permission and no unrelated account
permission.

- Environment variable: `JUNJO_MIRROR_APP_ID`
- Environment secret: `JUNJO_MIRROR_APP_PRIVATE_KEY`
- Repository variables:
  - `JUNJO_MINIMAL_MIRROR=mdrideout/junjo-ai-studio-minimal-build`
  - `JUNJO_VM_CADDY_MIRROR=mdrideout/junjo-ai-studio-deployment-example`
- Allowed ref: `studio-v*` tags.

A fine-grained personal access token restricted to those two repositories and
contents write is an acceptable temporary fallback. Do not use a classic
account-wide token. The workflow's normal `GITHUB_TOKEN` cannot write to other
repositories.

### `studio-live-model-tests`

Purpose: optional provider integration tests that intentionally make live model
requests.

- Optional secrets:
  - `OPENAI_API_KEY`
  - `ANTHROPIC_API_KEY`
  - `GEMINI_API_KEY`
- Trigger: manual dispatch or an explicitly approved schedule.
- Never required for pull-request merge.
- Never referenced by ordinary Studio, deployment, or Agent deterministic CI.

Do not recreate `JUNJO_SESSION_SECRET` or `JUNJO_SECURE_COOKIE_KEY` as GitHub
secrets for tests. Use fixed, clearly non-production fixture values in CI.

### `website-staging` and `website-production`

The existing Cloudflare Git integration remains the deployment mechanism, so no
Cloudflare API token is required in GitHub Actions. GitHub runs website build
validation; Cloudflare creates previews and production deployments.

If deployment is deliberately moved to Wrangler later, create a separate ADR
and use environment-scoped, project-limited Cloudflare credentials. Do not run
both Git integration and direct-upload production deployment concurrently.

## Repository-Committable Workflow Work

### Stable required checks

Do not require a workflow that can be skipped entirely by top-level path
filters. GitHub leaves a required but skipped workflow pending.

Implement an always-triggered pull-request gate:

1. A path-detection job determines whether Python, Studio, telemetry,
   deployments, website, licensing, or platform files changed.
2. Affected validation jobs run or call reusable component workflows.
3. Unaffected expensive jobs skip at job level rather than skipping the entire
   workflow.
4. A final `required` job uses `if: always()` and fails if any required affected
   job failed or was cancelled.
5. The final job always emits the same status-check name.

Target required checks:

- `Platform Gate / required`
- `Gitleaks Scan`

Keep component job names visible for diagnostics, but do not make a
path-filtered component workflow a required branch-protection context.

### Pull-request workflow rules

- No publishing credentials.
- No live model credentials.
- Fixed non-production application test secrets only.
- Explicit `permissions: contents: read`.
- Timeouts on every expensive job.
- Path detection includes workflow files and validation tooling that can change
  the meaning of a check.
- Deployment validation covers Compose, setup wizards, `.env`/`.env.bak`
  exclusion, version pins, Caddy, archives, and demo telemetry.
- Website validation covers locked install, static checks, build, links, and
  obsolete Junjo terminology.

### Production workflow rules

- Every production job references exactly one owning environment.
- Production Studio releases serialize and do not cancel in progress.
- Website previews may cancel superseded builds; Cloudflare production remains
  single-source through Git integration.
- Mirror publication serializes per destination repository.
- Privileged third-party actions are pinned to immutable commit SHAs before the
  repository enables required action SHA pinning.
- Dependabot is configured to propose GitHub Actions updates after pinning.

## Studio Release DAG

The previous standalone release workflow promoted floating Docker tags before
deployment and mirror validation. The monorepo implementation replaces it with
this ordering:

1. Validate `studio-v<version>` against `apps/studio/VERSION` and confirm the
   release commit is reachable from `master`.
2. Run Studio component tests and all deployment validation without production
   credentials.
3. Build and push each architecture by content digest, without assigning a
   mutable architecture tag.
4. Assemble candidate multi-platform manifests, preflight all version and
   source-SHA tags across all three services, then publish exact tags only when
   absent or already resolving to the identical digest.
5. Run clean deployment smoke tests against the exact version.
6. Build both self-contained archives and verify inventories, license files,
   generated-source metadata, and exclusion of `.env` and `.env.bak`.
7. Stage archives, hashes, image digests, and provenance as workflow artifacts.
8. Mint a short-lived GitHub App installation token.
9. Publish each deployment directory one way to its mirror.
10. Verify each mirror tree and source metadata against the monorepo source SHA.
11. Promote `major.minor` and `latest` image manifests only after distribution
    verification succeeds.
12. Update Docker Hub descriptions.
13. Create the GitHub release last and attach image evidence, archives, export
    reports, and a complete release-evidence document containing source SHA,
    workflow URL, image digests, archive hashes, tree hashes, and mirror
    commits.

A distribution failure prevents floating-tag promotion and release finalization.
Exact version/SHA images already pushed remain immutable evidence and may be
superseded only by a corrective release.

Add a manual dry-run mode that performs validation and builds inspected
artifacts but does not push images, update mirrors, promote tags, or publish a
release.

## Distribution Export Contract

Each exported mirror root contains:

- the deployment files;
- Apache-2.0 `LICENSE`;
- a generated-source notice;
- source repository URL;
- canonical source path;
- source commit SHA;
- Studio version;
- compatible SDK version where the example declares one.

The export process:

1. creates a fresh temporary directory;
2. copies only tracked canonical distribution content;
3. rejects `.env`, `.env.bak`, `.dbdata`, certificates, keys, caches, and build
   output;
4. validates the export outside the monorepo;
5. calculates a deterministic inventory/tree digest;
6. publishes a normal forward commit to the mirror;
7. verifies the remote default-branch tree after push.

No mirror commit is imported back into canonical source.

## Cloudflare Pages Cutover

### Python API documentation

Update the `junjo-python-api` Pages project:

- repository: `mdrideout/junjo`
- production branch: `master`
- root directory: `sdks/python`
- build: install locked documentation dependencies and run Sphinx
- output directory: `docs/_build/html` relative to the configured root
- include build-watch paths:
  - `sdks/python/*`
  - `contracts/telemetry/*` when contract docs affect the site
  - relevant root workflow/tooling paths
- preserve custom domain: `python-api.junjo.ai`

Validate a preview before merging the source move. After merge, verify the
custom domain, TLS, index, API pages, static assets, sitemap, and existing deep
links.

### Junjo website

Update the `junjo-website` Pages project:

- repository: `mdrideout/junjo`
- production branch: `master`
- root directory: `apps/website`
- install/build from the website's own lock and scripts
- output directory: `dist` relative to the configured root
- include build-watch paths:
  - `apps/website/*`
  - platform documentation paths intentionally consumed by the site
- preserve custom domain: `junjo.ai`

Validate a monorepo preview first. Disconnect the old
`mdrideout/junjo-website` integration only after the monorepo production
deployment passes domain, TLS, redirects, assets, sitemap, robots, and deep-link
checks.

## PyPI Trusted Publisher Cutover

Before the next Python release:

1. Open the PyPI `junjo` project publishing settings.
2. Add or update the GitHub publisher:
   - owner `mdrideout`
   - repository `junjo`
   - workflow `python-publish.yml`
   - environment `pypi`
3. Confirm the GitHub `pypi` environment is restricted to `sdk-python-v*` tags.
4. Run the full package build and metadata validation without publishing.
5. Use TestPyPI for an OIDC rehearsal if a production release is not due.
6. Publish the next normal version and record the workflow and PyPI URL.
7. Remove obsolete publisher entries only after the new identity succeeds.

PyPI versions cannot be reused. Recovery from a publication problem is a new
corrective package version.

## Branch Protection Cutover

Do not update required contexts before the new context has completed on a pull
request commit.

1. Open a migration pull request.
2. Run every new workflow and resolve all failures.
3. Confirm `Platform Gate / required` and `Gitleaks Scan` appear on the PR head.
4. Snapshot existing branch protection.
5. Replace `library-health` with the stable platform-gate context.
6. Retain:
   - strict up-to-date branch requirement;
   - administrator enforcement;
   - conversation resolution;
   - force-push prohibition;
   - branch-deletion prohibition.
7. If review requirements are enabled, account for the solo-maintainer workflow;
   do not configure an impossible self-approval policy.
8. Verify an unaffected documentation PR can pass without a pending component
   workflow.
9. Verify Python, Studio, contract, deployment, and website test PRs each run
   their owning checks.

## Repository Cutover Sequence

### Gate A: Repository-complete

- [x] All three source histories imported and recorded.
- [x] Current Junjo-owned source and artifacts are Apache-2.0.
- [x] `.env.bak` is ignored and excluded everywhere it can be created.
- [x] Stable required gate implemented.
- [x] Website and deployment CI implemented.
- [ ] Studio dry-run release and distribution export pass.
- [ ] Python publish dry run passes.
- [x] Combined-history secret scan passes.
- [x] Root and scoped documentation match implementation.

Agent implementation may resume after Gate A. External credentials and hosting
do not block repository architecture work.

### Gate B: Configure production control plane

- [ ] Snapshot destination and old-repository GitHub settings.
- [ ] Configure GitHub environments and ref policies.
- [ ] Recreate/rotate only approved environment credentials.
- [ ] Configure PyPI trusted publisher.
- [ ] Install the mirror GitHub App on exactly two repositories.
- [ ] Configure Cloudflare monorepo roots and preview paths.
- [ ] Run every deployment against a preview, temporary branch, or temporary
  repository.
- [ ] Update required checks only after stable contexts exist.

### Gate C: Production cutover

- [ ] Merge the validated migration.
- [ ] Verify default-branch CI.
- [ ] Verify both Cloudflare production projects.
- [ ] Perform the first destination Studio release.
- [ ] Verify exact image manifests and digests.
- [ ] Verify both release archives from clean extraction.
- [ ] Verify both mirrors from fresh clones.
- [ ] Verify generated-source SHAs and tree digests.
- [ ] Perform the next Python release or TestPyPI trusted-publisher proof.

### Gate D: Retire competing sources

- [ ] Update old Studio and website default branches with Apache-2.0 and
  canonical-source/archive notices.
- [ ] Disable every old Studio workflow.
- [ ] Delete old Studio repository secrets after destination publication works.
- [ ] Archive the old Studio source repository.
- [ ] Disconnect and archive the old website source repository after Cloudflare
  production observation.
- [ ] Keep both deployment repositories unarchived as generated distributions.
- [ ] Keep the minimal repository as a template.
- [ ] Decide and record whether VM/Caddy is also a template.
- [ ] Redirect contribution instructions and issues to the monorepo.

## GitHub Settings Evidence Commands

These commands inventory names and settings, never secret values:

```bash
gh repo view mdrideout/junjo \
  --json nameWithOwner,visibility,defaultBranchRef,url
gh secret list --repo mdrideout/junjo
gh variable list --repo mdrideout/junjo
gh api repos/mdrideout/junjo/environments
gh api repos/mdrideout/junjo/actions/permissions
gh api repos/mdrideout/junjo/actions/permissions/workflow
gh api repos/mdrideout/junjo/branches/master/protection
gh workflow list --repo mdrideout/junjo --all
```

Run the same inventory for the old Studio, website, and distribution
repositories before and after cutover. Store sanitized JSON or a concise result
summary in the migration record; do not commit access tokens or secret values.

## Post-Cutover Verification

Record:

- migration PR and merge commit;
- successful required-check run URLs;
- GitHub environment names and ref policies;
- secret and variable names only;
- PyPI trusted-publisher identity and first successful run;
- Studio release workflow URL;
- exact Docker image digests;
- distribution archive SHA-256 values;
- canonical source commit and mirror commit for each distribution;
- clean-clone Compose and demo smoke results;
- Cloudflare project deployment IDs and source commits;
- custom-domain/TLS verification;
- old workflow disablement and repository archival state.

## Rollback

### Before production cutover

Revert or fix the migration branch normally. Do not change old source or hosting
integrations.

### Website or documentation

Promote the last known-good Cloudflare deployment and reconnect the prior Git
integration if it has not yet been archived. Do not delete the last good
deployment during cutover.

### Distribution mirrors

Restore the last known-good exported content with a new forward commit. Do not
force-push mirror history during rollback.

### Docker Hub

Exact version and source-SHA tags remain immutable. Repoint only floating
`major.minor` and `latest` manifests to the last known-good digests, then issue a
corrective Studio release.

### PyPI

Published versions cannot be reused. Fix the trusted-publisher identity or
package issue and publish a new corrective version.

### Branch protection

Use the saved protection snapshot to restore the previous contexts if the new
stable gate is defective. Never remove all protection as a convenience
workaround.

## Completion

GitHub and hosting cutover is complete only when canonical source, required
checks, environments, least-privilege credentials, releases, mirrors,
Cloudflare deployments, external repository status, evidence, and rollback
paths all agree with ADR 0001.

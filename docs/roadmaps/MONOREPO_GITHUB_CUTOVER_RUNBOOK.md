# Junjo Monorepo GitHub And Hosting Cutover Runbook

## Status

Approved implementation runbook.

This document turns Phases 6 through 8 of `MONOREPO_MIGRATION_PLAN.md` into an
executable repository and operator cutover. It covers GitHub Actions, required
checks, environments, credentials, PyPI trusted publishing, Docker Hub,
deployment-distribution mirrors, Cloudflare Pages, old-repository shutdown,
verification, and forward recovery.

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
- Production downtime, preview continuity, backward compatibility, and old
  deployment rollback are not migration gates. Merge the validated repository
  first, then replace external configuration directly.
- Do not move, overwrite, or delete an immutable package or image version.
  Recover with a forward fix or corrective release.
- Do not force-push generated distribution history during ordinary publication.

## Current Control-Plane Inventory

Snapshot date: 2026-07-13.

### Destination repository

`mdrideout/junjo` currently has:

- public visibility and `master` as the default branch;
- no repository Actions secrets;
- no repository Actions variables select publication destinations; exact image
  and mirror targets live in `tooling/studio_release_contract.json`;
- `pypi`, `studio-dockerhub-production`,
  `studio-distributions-production`, and `studio-release-production` exist with
  tag-only deployment policies;
- those four environments currently contain no secrets;
- `studio-dockerhub-production` does not yet contain the
  `STUDIO_RELEASE_AUTHORITY_CUTOVER` confirmation;
- read-only default `GITHUB_TOKEN` permissions;
- all GitHub Actions allowed and no repository-level SHA-pin requirement;
- strict `master` protection with administrator enforcement and conversation
  resolution;
- required checks named `required` and `Gitleaks Scan`;
- no repository rulesets.

The migration branch contains the new monorepo workflows, but they are not
active as default-branch workflows until merged.

The public Docker Hub repository API currently reports immutable tags disabled
on the backend, frontend, and ingestion repositories (`enabled: false`, retained
rule `.*`). The release workflow intentionally refuses its first registry
mutation until Gate B replaces that state with the two exact contract-owned
rules and the exclusive-authority confirmation is present.

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
- Environment variable:
  - `STUDIO_RELEASE_AUTHORITY_CUTOVER=mdrideout/junjo`
- Allowed ref: `studio-v*` tags.
- Jobs: release-authority and live immutable-rule preflight, image architecture
  push, manifest creation/promotion, and Docker Hub description update only.

Create a new least-privilege Docker Hub token rather than reusing an unknown
repository-secret value when possible.

Do not create the authority variable until every old Studio release workflow
and Docker Hub autobuild is disabled. Configure each of the three contract-owned
Docker Hub repositories with **specific immutable tags** and exactly these Go/RE2
rules:

- `^[0-9]+\.[0-9]+\.[0-9]+$`
- `^[0-9a-f]{40}$`

This leaves `major.minor`, `latest`, and run-scoped candidate tags mutable while
making stable versions and full source revisions registry-enforced write-once
identities. The production workflow reads the live Docker Hub repository
settings and fails before its first image mutation if any repository identity,
enabled flag, or rule differs. See Docker's
[immutable tags documentation](https://docs.docker.com/docker-hub/repos/manage/hub-images/immutable-tags/).

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
- Allowed ref: `studio-v*` tags.

The GitHub App is the only supported mirror-publishing identity. The workflow's
normal `GITHUB_TOKEN` cannot write to other repositories, and personal access
tokens are not a fallback path.

### `studio-release-production`

Purpose: authorize the final GitHub release after all immutable images,
deployment mirrors, floating tags, descriptions, and evidence have completed.

- Stored secrets: none.
- Allowed ref: `studio-v*` tags.
- Job: final release-evidence validation and GitHub release creation only.
- Required workflow permission: `contents: write` on that job only.

This environment does not grant Docker or mirror credentials. It separates the
final repository mutation from both external publishing authorities.

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

- `Platform Gate / required` in the pull-request UI (`required` as the branch
  protection API context)
- `Gitleaks Scan`

Keep component job names visible for diagnostics, but do not make a
path-filtered component workflow a required branch-protection context.

### Pull-request workflow rules

- No publishing credentials.
- The platform gate is the sole pull-request caller for reusable component
  workflows; component workflows retain path-filtered `push`, manual, and
  `workflow_call` triggers without duplicate direct pull-request triggers.
- When deployment or release ownership is affected, the shared Studio release
  validation workflow owns admission, Studio, telemetry, deployment, and dry
  build checks. The gate skips the corresponding direct jobs; component-only
  changes still use direct routing. The write-capable publisher is not reusable
  and is never part of the pull-request workflow graph.
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

- Every credentialed or externally mutating production job references exactly
  one owning environment. Admission, tests, and registry smoke remain
  uncredentialed.
- Production Studio releases serialize and do not cancel in progress.
- Registry mutation waits for the protected exclusive-authority assertion and
  live Docker Hub immutable-tag proof.
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

1. Validate `studio-v<version>` against `apps/studio/VERSION`, confirm the
   release commit is reachable from `master`, and bind the fetched live tag
   target to that source revision.
2. Run Studio component tests and all deployment validation without production
   credentials.
3. Confirm the old publisher is disabled and this monorepo is the exclusive
   release authority; validate the live contract-owned immutable-tag rules on
   all three Docker Hub repositories.
4. Build and push each architecture by content digest, without assigning a
   mutable architecture tag.
5. Assemble candidate multi-platform manifests, preflight all version and
   source-SHA tags across all three services, then publish exact tags only when
   absent or already resolving to the identical digest. Registry-side rules
   reject a competing writer instead of allowing an overwrite.
6. Run clean deployment smoke tests against the exact digests.
7. Validate both mirror identities and default branches together without mirror
   mutation credentials.
8. Mint a short-lived GitHub App installation token and revalidate both mirror
   destinations with it before either push.
9. Build both self-contained archives and verify inventories, license files,
   generated-source metadata, and exclusion of `.env` and `.env.bak`.
10. Publish each deployment directory one way to its mirror.
11. Verify each mirror tree and source metadata against the monorepo source SHA.
12. Stage archives, mirror reports, hashes, image digests, and provenance as
    stable same-run workflow artifacts.
13. Promote `major.minor` and `latest` image manifests only after distribution
    verification succeeds.
14. Update Docker Hub descriptions.
15. Revalidate source reachability and the live tag target, then create the
    GitHub release last and attach image evidence, archives, export reports, and
    a complete release-evidence document containing source SHA, workflow URL,
    image digests, archive hashes, tree hashes, and mirror commits.

A distribution failure prevents floating-tag promotion and release finalization.
Exact version/SHA images already pushed remain immutable evidence and may be
superseded only by a corrective release.

Each evidence producer owns one stable artifact name within the workflow run
and overwrites only that artifact when it reruns. Every production job compares
the attempt recorded by admission with its current workflow attempt. Do not use
"Re-run failed jobs" for a production release: it fails closed because its
successful admission and live-control jobs would be stale. Use "Re-run all
jobs" so admission, Docker Hub controls, and all producer evidence are refreshed.
Evidence from another workflow run is never selected.

The manual publisher and pull-request gate both call the same read-only
`studio-release-validation.yml` workflow. It performs admission, component and
deployment validation, and inspected dry builds without publishing credentials.
`studio-docker-publish.yml` is a top-level tag/manual workflow only; its
write-capable jobs cannot enter a pull-request reusable-workflow graph.

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

## Studio artifact license evidence

Studio treats artifact licensing as a reviewable release input rather than an
inference from the repository root license. Each backend, frontend, and
ingestion production image must contain Junjo's `LICENSE`,
`THIRD_PARTY_NOTICES.md`, and the component evidence defined by ADR 0002.

Before approving the first release, and after every production dependency
change:

1. Run
   `python3 tooling/scripts/validate_studio_artifact_licenses.py check --with-cargo-metadata`.
2. Run `npm ci && npm run build` from `apps/studio/frontend`, then run
   `python3 ../../../tooling/scripts/validate_studio_artifact_licenses.py check --verify-installed-frontend --frontend-dist dist`.
3. Review the frontend and ingestion inventory diffs, including new packages,
   license expressions, and the exact evidence for manual overrides.
4. Determine whether upstream copyright notices or license texts beyond the
   committed Studio notice must be added to the artifact.
5. Inspect all three built production images and record the paths and hashes of
   their `/usr/share/licenses/junjo-ai-studio/` contents.
6. Record the reviewer, source commit, inventory hashes, image digests, and
   decision in `MONOREPO_MIGRATION_RECORD.md`.

The validator proves lock binding, dependency selection, reviewed expression
sets, manual evidence, image copy declarations, and source-map exclusion. It
does not make a legal conclusion or approve a release.

## Cloudflare Pages Cutover

Merge the validated migration before changing Cloudflare. The failing legacy
Cloudflare check on pull request 12 is not a merge gate because it evaluates the
new tree with obsolete project settings. No temporary Pages projects, preview
rehearsal, deployment freeze, or old-project fallback is required. After the
merge, update both existing Pages projects directly and fix any deployment
failure forward on `master`.

### Python API documentation

Update the existing `junjo-python-api` Pages project with these settings:

- repository: `mdrideout/junjo`
- production branch: `master`
- root directory: `sdks/python`
- runtime variable: `PYTHON_VERSION=3.13`
- build command:
  `python -m pip install uv==0.11.7 && uv sync --frozen --package junjo --extra dev && uv run sphinx-build -W -b html docs docs/_build/html`
- output directory: `docs/_build/html` relative to the configured root
- include build-watch paths:
  - `sdks/python/*`
  - `contracts/telemetry/*` when contract docs affect the site
  - relevant root workflow/tooling paths
- production custom domain: `python-api.junjo.ai`

Trigger a production deployment and verify the domain, TLS, index, API pages,
static assets, sitemap, and deep links. If it fails, correct `master` or the
Pages settings and deploy again.

### Junjo website

Update the existing `junjo-website` Pages project with these settings:

- repository: `mdrideout/junjo`
- production branch: `master`
- root directory: `apps/website`
- runtime variable: `NODE_VERSION=22.12.0`
- build command: `npm ci && npm run build && npm run validate:build`
- output directory: `dist` relative to the configured root
- include build-watch paths:
  - `apps/website/*`
  - platform documentation paths intentionally consumed by the site
- production custom domain: `junjo.ai`

Trigger a production deployment and verify the domain, TLS, redirects, assets,
sitemap, robots, and deep links. Disconnect the old
`mdrideout/junjo-website` integration; if the new deployment fails, correct the
monorepo or Pages settings and deploy again.

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
5. Publish the next normal version and record the workflow and PyPI URL.
6. Remove obsolete publisher entries.

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

### Gate A: Merge the repository

- [x] All planned source histories imported and recorded.
- [x] Current Junjo-owned source, package metadata, and OCI metadata declare
  Apache-2.0; Studio lock-bound artifact inventories and notices are present.
- [x] Complete and record an artifact-license review of the first built Studio
  images, including copyright/license-text obligations for bundled frontend
  and statically linked Rust dependencies.
- [x] `.env`, `.env.bak`, and interrupted private staging files are ignored and
  excluded everywhere they can be created.
- [x] Stable required gate implemented.
- [x] Website and deployment CI prove their complete current contracts.
- [x] Studio dry-run release and distribution export pass.
- [x] Python local package build and Twine validation pass.
- [x] Combined-history and current-tree secret scans pass after remediation.
- [x] Root and scoped documentation are prepared and locally validated.
- [x] Record final pull-request revision `afc5db6` and successful Platform Gate
  and Gitleaks runs in the migration record.
- [x] Record the license holder's confirmed Tailwind UI/Plus purchase and
  historical Studio end-product use; retain the imported commits and tags under
  their applicable historical licenses as decided by ADR 0002.
- [ ] Merge pull request 12 with a merge commit, not squash or rebase.
- [ ] Verify required checks on `master`.

The obsolete Cloudflare pull-request check is explicitly non-blocking. Merge is
the first remaining operator action.

### Gate B: Replace external control-plane configuration

- [x] Configure GitHub environments and ref policies.
- [ ] Recreate/rotate only approved environment credentials.
- [ ] Disable every old Studio release workflow and Docker Hub autobuild, remove
  its Docker publishing authority, and record the settings evidence.
- [ ] Configure and verify the two contract-owned Docker Hub immutable-tag
  rules on the backend, frontend, and ingestion repositories.
- [ ] Only after those two checks, set
  `STUDIO_RELEASE_AUTHORITY_CUTOVER=mdrideout/junjo` in
  `studio-dockerhub-production`.
- [ ] Configure PyPI trusted publisher.
- [ ] Install the mirror GitHub App on exactly two repositories.
- [ ] Reconfigure both existing Cloudflare Pages projects directly against
  `mdrideout/junjo` `master` using the component roots above.
- [x] Verify required checks are exactly `required` and `Gitleaks Scan` after
  their stable contexts exist.
- [ ] Enable repository action-SHA enforcement after the merged workflow set is
  present and record the settings response.
- [ ] Add and verify an immutable `studio-v*` tag ruleset, or record the exact
  GitHub plan/API limitation that prevents it.

### Gate C: Publish and verify

- [ ] Verify both Cloudflare production projects.
- [ ] Perform the first destination Studio release.
- [ ] Verify exact image manifests and digests.
- [ ] Verify both release archives from clean extraction.
- [ ] Verify both mirrors from fresh clones.
- [ ] Verify generated-source SHAs and tree digests.
- [ ] Perform the next Python release.

### Gate D: Retire competing sources

- [ ] Update the old website default branch with Apache-2.0 and a
  canonical-source/archive notice.
- [ ] Update the old Studio default branch with a canonical-source/archive
  notice that preserves the Tailwind Plus boundary; do not relabel retained
  Catalyst-derived source as Apache-2.0.
- [ ] Disable every remaining non-release old Studio workflow.
- [ ] Delete remaining old Studio repository secrets.
- [ ] Archive the old Studio source repository.
- [ ] Disconnect and archive the old website source repository.
- [ ] Keep both deployment repositories unarchived as generated distributions.
- [ ] Keep the minimal repository as a template.
- [ ] Decide and record whether VM/Caddy is also a template.
- [ ] Redirect contribution instructions and issues to the monorepo.

## GitHub Settings Evidence Commands

These commands inventory names and settings, never secret values:

```bash
gh repo view mdrideout/junjo \
  --json nameWithOwner,visibility,defaultBranchRef,url
gh secret list --repo mdrideout/junjo --json name --jq '.[].name'
gh variable list --repo mdrideout/junjo --json name --jq '.[].name'
gh api repos/mdrideout/junjo/environments
for environment in pypi studio-dockerhub-production studio-distributions-production studio-release-production; do
  gh secret list --repo mdrideout/junjo --env "$environment" --json name --jq '.[].name'
  gh variable list --repo mdrideout/junjo --env "$environment" --json name --jq '.[].name'
done
gh api repos/mdrideout/junjo/actions/permissions
gh api repos/mdrideout/junjo/actions/permissions/workflow
gh api repos/mdrideout/junjo/branches/master/protection
gh api repos/mdrideout/junjo/rulesets --paginate
gh workflow list --repo mdrideout/junjo --all
```

Record the live Docker Hub identity and immutability settings without tokens:

```bash
for image in \
  mdrideout/junjo-ai-studio-backend \
  mdrideout/junjo-ai-studio-frontend \
  mdrideout/junjo-ai-studio-ingestion; do
  namespace="${image%%/*}"
  repository="${image#*/}"
  curl --fail --silent --show-error --proto '=https' --tlsv1.2 \
    "https://hub.docker.com/v2/namespaces/${namespace}/repositories/${repository}" |
    jq '{namespace, name, immutable_tags_settings}'
done
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

## Forward-only recovery

Cutover failures are fixed in the monorepo and redeployed. Distribution mirrors
receive a new forward commit. Exact Docker version/source tags and published
PyPI versions are never reused; issue a corrective Studio or Python release.
Do not restore old source repositories, old publishers, compatibility paths, or
parallel production authorities.

## Completion

GitHub and hosting cutover is complete only when canonical source, required
checks, environments, least-privilege credentials, releases, mirrors,
Cloudflare deployments, external repository status, and evidence all agree with
ADR 0001.

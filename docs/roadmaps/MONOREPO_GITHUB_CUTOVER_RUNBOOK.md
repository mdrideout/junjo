# Junjo Monorepo GitHub And Hosting Cutover Runbook

## Status

Approved implementation runbook.

This document turns Phases 6 through 8 of `MONOREPO_MIGRATION_PLAN.md` into an
executable repository and operator cutover. It covers GitHub Actions, required
checks, environments, credentials, PyPI trusted publishing, Docker Hub,
deployment-distribution mirrors, Cloudflare Pages, old-repository shutdown,
verification, and forward recovery.

The repository is merged. Operators should begin at
[Gate B](#gate-b-replace-external-control-plane-configuration). Detailed
sections above that checklist explain the purpose, exact provider UI location,
change, and verification for every remaining item.

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
- read-only default `GITHUB_TOKEN` permissions;
- all GitHub Actions allowed and no repository-level SHA-pin requirement;
- strict `master` protection with administrator enforcement and conversation
  resolution;
- required checks named `required` and `Gitleaks Scan`;
- no repository rulesets.

The new monorepo workflows are active on `master` after merge commit
`02f34073ceb40963e716498cf2caaaddafa2db28`.

The public Docker Hub repository API currently reports immutable tags disabled
on the backend, frontend, and ingestion repositories (`enabled: false`, retained
rule `.*`). The release workflow intentionally refuses its first registry
mutation until Gate B replaces that state with the two exact contract-owned
rules.

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

GitHub environments are not servers and they do not deploy anything by
themselves. They are named security boundaries used by the workflows in
`.github/workflows`. An environment answers two questions:

1. which release refs may run a production job; and
2. which credentials that job may read.

Open the destination repository and navigate to **Settings > Environments**:

<https://github.com/mdrideout/junjo/settings/environments>

The four required environments and their tag policies already exist. Their
credential stores are empty after the merge. Populate only the two environments
that need external credentials:

| Environment | Why it exists | What the operator changes |
| --- | --- | --- |
| `studio-dockerhub-production` | Allows Studio release jobs to push the three production images. | Add the Docker Hub username and token. |
| `studio-distributions-production` | Allows the release job to replace the contents of the two generated deployment-mirror repositories. | Add a narrowly installed GitHub App ID and private key. |
| `studio-release-production` | Separates final GitHub Release creation from image and mirror publication. | Nothing. It deliberately has no secrets. |
| `pypi` | Binds PyPI's short-lived OIDC token to the Python publishing job. | Nothing in GitHub. Configure the matching publisher on PyPI. |

Environment secrets are encrypted credentials. Environment variables are
non-secret configuration and can appear in logs. Do not put tokens or private
keys in variables.

### Configure `studio-dockerhub-production`

**Purpose:** give only Studio production jobs access to Docker Hub.

**Where:** **Junjo repository > Settings > Environments >
`studio-dockerhub-production`**.

**Before publishing:**

1. In `mdrideout/junjo-ai-studio`, open **Actions > Publish Docker Images**, use
   the workflow menu, and choose **Disable workflow**.
2. In that old repository, open **Settings > Secrets and variables > Actions**
   and delete `DOCKERHUB_USERNAME` and `DOCKERHUB_TOKEN`. This makes an accidental
   re-enable harmless.
3. In Docker Hub, open each of these repositories and check **Builds > Configure
   automated builds**. Disable every Autobuild rule:
   - `mdrideout/junjo-ai-studio-backend`
   - `mdrideout/junjo-ai-studio-frontend`
   - `mdrideout/junjo-ai-studio-ingestion`
4. In each Docker Hub repository, open **Settings > General > Tag mutability
   settings**, select **Specific tags are immutable**, and add exactly:
   - `^[0-9]+\.[0-9]+\.[0-9]+$`
   - `^[0-9a-f]{40}$`

The first rule makes stable release versions such as `0.81.2` write-once. The
second makes full source-commit tags write-once. `latest`, `0.81`, and temporary
candidate tags remain movable because the release workflow promotes them only
after verification. Docker documents this control under
[immutable tags](https://docs.docker.com/docker-hub/repos/manage/hub-images/immutable-tags/).

**Then configure GitHub:**

1. In Docker Hub, open **Avatar > Account settings > Personal access tokens >
   Generate new token**. Name it for the Junjo monorepo release workflow, set a
   deliberate expiration, and choose **Read & Write**. The `mdrideout` namespace
   is a personal namespace, so Docker PATs are account-scoped rather than
   repository-scoped; do not grant Delete permission. Docker documents this UI
   under [personal access tokens](https://docs.docker.com/security/access-tokens/).
2. Under **Environment secrets**, add:
   - `DOCKERHUB_USERNAME`: the Docker Hub account name;
   - `DOCKERHUB_TOKEN`: the new token, not the account password.

**Verify:** return to the environment page and confirm the two secret *names*
are listed. Do not print secret values. The first release also queries the
public Docker Hub settings and fails before pushing if any immutable rule
differs from the contract.

### Configure `studio-distributions-production`

**Purpose:** allow a release to publish generated copies of the canonical
deployment directories to two standalone repositories. A normal repository
`GITHUB_TOKEN` cannot write to other repositories. A dedicated GitHub App gives
the workflow a short-lived token limited to exactly those mirrors, without
using a maintainer's personal access token.

**Where to create the App:** GitHub profile picture > **Settings > Developer
settings > GitHub Apps > New GitHub App**. A direct starting point is
<https://github.com/settings/apps>.

Create a private App, for example `junjo-studio-distribution-publisher`, with:

- webhook disabled;
- repository permission **Contents: Read and write**;
- no account permissions and no other repository write permissions.

After creation:

1. On the App settings page, note the **App ID**. Do not use the Client ID.
2. Generate one private key and retain the downloaded PEM only long enough to
   store it in GitHub.
3. Choose **Install App**, select **Only select repositories**, and install it
   on exactly:
   - `mdrideout/junjo-ai-studio-minimal-build`
   - `mdrideout/junjo-ai-studio-deployment-example`
4. Open **Junjo repository > Settings > Environments >
   `studio-distributions-production`**.
5. Under **Environment variables**, add `JUNJO_MIRROR_APP_ID` with the numeric
   App ID.
6. Under **Environment secrets**, add `JUNJO_MIRROR_APP_PRIVATE_KEY` with the
   complete PEM file contents, including its begin/end lines.

GitHub documents the installation scoping under
[installing your own GitHub App](https://docs.github.com/en/apps/using-github-apps/installing-your-own-github-app)
and private-key creation under
[managing GitHub App private keys](https://docs.github.com/en/apps/creating-github-apps/authenticating-with-a-github-app/managing-private-keys-for-github-apps).

**Verify:** the App installation page lists only the two mirrors, and the
environment page lists the variable and secret names. Do not manually edit the
mirrors after this cutover; `apps/studio/deployments` is canonical.

### Verify `studio-release-production`

**Purpose:** the last workflow job creates the GitHub Release only after image,
archive, mirror, and provenance evidence succeeds. It uses the job-scoped
`GITHUB_TOKEN`; no external credential belongs here.

**Where:** **Junjo repository > Settings > Environments >
`studio-release-production`**.

Confirm that it allows only `studio-v*` tags and has no secrets or variables.
No value needs to be added.

### Configure the PyPI trust relationship

**Purpose:** let PyPI issue a short-lived token only to the exact Junjo workflow
and environment. No permanent PyPI token is stored in GitHub.

**GitHub side:** **Junjo repository > Settings > Environments > `pypi`**. It
already allows only `sdk-python-v*` tags and must remain empty.

**PyPI side:** sign in to PyPI, open **Your projects > junjo > Manage >
Publishing**, and add a GitHub Actions trusted publisher with:

- owner: `mdrideout`
- repository: `junjo`
- workflow filename: `python-publish.yml`
- environment: `pypi`

PyPI documents this UI under
[adding a publisher to an existing project](https://docs.pypi.org/trusted-publishers/adding-a-publisher/).
After the new publisher appears, remove the obsolete publisher for workflow
`publish.yml` or the old repository.

**Verify:** PyPI lists the exact four fields above and GitHub's `pypi`
environment contains no PyPI token.

### GitHub settings that are controls, not credentials

Two remaining repository settings protect the workflow definitions and release
tags themselves.

1. Open **Junjo repository > Settings > Actions > General**. Under **Actions
   permissions**, enable **Require actions to be pinned to a full-length commit
   SHA**. Purpose: a third-party action tag cannot be silently moved to new
   code. The merged workflows already use full commit SHAs. GitHub documents
   this under
   [repository Actions settings](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/enabling-features-for-your-repository/managing-github-actions-settings-for-a-repository).
2. Open **Junjo repository > Settings > Rules > Rulesets > New ruleset > New tag
   ruleset**. Name it `immutable-studio-release-tags`, target tags matching
   `studio-v*`, set enforcement to **Active**, and enable **Restrict updates**
   and **Restrict deletions**. Do not restrict creation. Purpose: a published
   release tag remains bound to the source commit used for images and evidence.
   GitHub documents the UI under
   [creating repository rulesets](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/creating-rulesets-for-a-repository).

Cloudflare remains the website deployment authority. Do not create GitHub
website deployment environments or Cloudflare API secrets for this cutover.

## Repository-Committable Workflow Work

### Stable required checks

The always-triggered pull-request gate runs only fast repository integrity
validation. It does not call component suites, deployment smoke, image builds,
or the Studio release rehearsal. A final `required` job uses `if: always()` and
emits one stable status-check name.

Target required checks:

- `Platform Gate / required` in the pull-request UI (`required` as the branch
  protection API context)
- `Gitleaks Scan`

Component workflows remain path-scoped on pushes to `master` and available for
manual execution. The complete Studio suite, deployment proof, dry builds, and
publication checks run as part of a `studio-v*` production release.

### Pull-request workflow rules

- No publishing credentials.
- Pull requests run repository invariants, tooling unit tests, actionlint,
  Zizmor, and Gitleaks only.
- Component and release-validation workflows are never called from the
  pull-request workflow graph.
- No live model credentials.
- Explicit `permissions: contents: read`.

### Production workflow rules

- Every credentialed or externally mutating production job references exactly
  one owning environment. Admission, tests, and registry smoke remain
  uncredentialed.
- Production Studio releases serialize and do not cancel in progress.
- Registry mutation waits for live Docker Hub immutable-tag proof.
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
3. Validate the live contract-owned immutable-tag rules on all three Docker Hub
   repositories.
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

The publisher calls the read-only `studio-release-validation.yml` workflow. It
performs admission, component and deployment validation, and inspected dry
builds before any publishing credential is used. `studio-docker-publish.yml` is
a top-level tag/manual workflow only; its write-capable jobs cannot enter the
pull-request workflow graph.

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

**Purpose:** make Cloudflare build both public sites from their canonical
monorepo directories on `master`. GitHub validates the builds; Cloudflare owns
hosting, custom domains, and automatic production deployment.

**First grant repository access:** on GitHub, open **Profile picture > Settings
> Applications > Installed GitHub Apps > Cloudflare Workers and Pages >
Configure**. Under repository access, ensure `mdrideout/junjo` is selected.
Without this access Cloudflare cannot clone the monorepo.

Cloudflare permits changing build settings on an existing Pages project, but it
does not permit changing that project's connected Git repository. Therefore:

- edit `junjo-python-api` in place because it already uses `mdrideout/junjo`;
- delete and recreate `junjo-website` because it uses the old standalone
  repository.

There is no temporary project or rollback path. If a deployment fails, fix its
settings or `master` and deploy forward. Cloudflare documents the repository
limitation under [Pages known issues](https://developers.cloudflare.com/pages/platform/known-issues/)
and monorepo roots under [Pages build configuration](https://developers.cloudflare.com/pages/configuration/build-configuration/).

### Python API documentation

**Where:** Cloudflare dashboard > **Workers & Pages > `junjo-python-api` >
Settings > Builds**. Edit the Git/build configuration to:

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

Add `PYTHON_VERSION` under **Settings > Environment variables** for both
production and preview if the UI scopes values by environment. Configure build
watch paths under **Settings > Builds > Build watch paths**.

**Verify:** trigger **Deployments > Create deployment/Retry deployment**, then
open `https://python-api.junjo.ai` and at least one deep API-documentation URL.
Confirm the deployment source is `mdrideout/junjo` `master`, not merely that the
old cached site still responds.

### Junjo website

The existing project is connected to `mdrideout/junjo-website`, so it cannot be
edited into the desired state.

**Where and action:**

1. In Cloudflare, open **Workers & Pages > `junjo-website` > Custom domains** and
   remove `junjo.ai`.
2. Open **Settings > Delete project** and delete the old project.
3. Return to **Workers & Pages > Create application > Pages > Connect to Git**.
4. Select `mdrideout/junjo`, name the project `junjo-website`, and configure:

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

5. Add `NODE_VERSION` under **Settings > Environment variables** for production
   and preview if scoped separately.
6. Configure the include paths under **Settings > Builds > Build watch paths**.
7. Allow the first production deployment to complete, then add `junjo.ai` under
   **Custom domains**.

**Verify:** open `https://junjo.ai`, `/sitemap-index.xml`, `/robots.txt`, and at
least one deep documentation route. In the Cloudflare deployment details,
confirm the source is `mdrideout/junjo` `master` and the root is `apps/website`.

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
- [x] Merge pull request 12 with merge commit
  `02f34073ceb40963e716498cf2caaaddafa2db28`.
- [x] All component workflows triggered by merge commit `02f3407` completed on
  `master`, including Gitleaks, Platform Integrity, Python, website, telemetry,
  Studio backend/ingestion/frontend/deployments, version sync, Proto, and REST.

The repository merge is complete. Start Gate B below.

### Gate B: Replace external control-plane configuration

Complete these controls before creating the first `studio-v0.81.2` tag. Each
item links to the detailed purpose, location, action, and verification above.

- [x] GitHub environments and tag policies exist. This only creates empty
  security boundaries; it does not provide credentials or enable publishing.
- [ ] [Transfer Docker publishing authority](#configure-studio-dockerhub-production):
  disable the old `Publish Docker Images` workflow, delete its Docker secrets,
  disable Docker Hub Autobuilds, configure both immutable-tag rules on all three
  image repositories, and add the new environment credentials.
- [ ] [Create and install the mirror GitHub App](#configure-studio-distributions-production),
  then store its App ID and private key in the distributions environment.
- [ ] [Configure PyPI Trusted Publishing](#configure-the-pypi-trust-relationship)
  for the next Python release. This is independent of the Studio release and
  does not require a GitHub secret.
- [ ] [Enable action SHA pinning and create the Studio tag ruleset](#github-settings-that-are-controls-not-credentials).
- [ ] [Reconfigure Cloudflare](#cloudflare-pages-cutover): edit Python docs in
  place, delete/recreate the website project from the monorepo, and verify both
  production domains.
- [x] Required pull-request checks are exactly `required` and `Gitleaks Scan`.

### Gate C: Publish and verify

- [ ] Confirm both Cloudflare deployment-detail pages identify
  `mdrideout/junjo` `master` and the correct component root.
- [ ] From an up-to-date local `master`, create and push the first Studio release
  tag. The version is read from `apps/studio/VERSION`:

  ```bash
  git switch master
  git pull --ff-only origin master
  VERSION="$(cat apps/studio/VERSION)"
  test "$VERSION" = "0.81.2"
  git tag -a "studio-v${VERSION}" -m "Junjo AI Studio ${VERSION}"
  git push origin "studio-v${VERSION}"
  ```

  The tag starts `.github/workflows/studio-docker-publish.yml`; do not manually
  run the workflow for a production release.
- [ ] In **Junjo repository > Actions > Publish Studio Release**, wait for the
  entire run. If it fails, correct the cause and use **Re-run all jobs**. Never
  use **Re-run failed jobs**, because production evidence is bound to one fresh
  workflow attempt.
- [ ] Open the resulting GitHub Release and verify it contains image digests,
  archive hashes, source SHA, mirror commits, and release evidence.
- [ ] In Docker Hub, verify `0.81.2` and the full source SHA resolve to the
  recorded immutable manifests, and `0.81`/`latest` resolve to the promoted
  release.
- [ ] Fresh-clone both mirror repositories and verify their generated-source
  notices identify the release source SHA and canonical monorepo path.
- [ ] For the next Python SDK release, update the version on `master`, publish a
  GitHub Release whose tag is exactly `sdk-python-v<pyproject version>`, and
  verify **Actions > Publish Python SDK to PyPI** and the PyPI project page.

### Gate D: Retire competing sources

After the Studio and website cutovers are proven, retire repositories that could
be mistaken for editable source. There is no observation or rollback period.

- [ ] In `mdrideout/junjo-ai-studio`, commit a short canonical-source/archive
  notice that points to `mdrideout/junjo/apps/studio` and preserves the
  historical Tailwind Plus boundary. Do not relabel historical
  Catalyst-derived source as Apache-2.0.
- [ ] Open **old Studio repository > Actions** and disable every remaining
  workflow. Open **Settings > Secrets and variables > Actions** and delete every
  remaining secret. Then open **Settings > General > Danger Zone > Archive this
  repository**.
- [ ] In `mdrideout/junjo-website`, commit Apache-2.0 and a canonical-source
  notice pointing to `mdrideout/junjo/apps/website`. Then open **Settings >
  General > Danger Zone > Archive this repository**.
- [ ] Keep `mdrideout/junjo-ai-studio-minimal-build` and
  `mdrideout/junjo-ai-studio-deployment-example` unarchived. They are generated
  release distributions, not editable sources. Keep the minimal repository as
  a GitHub template and decide whether VM/Caddy should also be a template.
- [ ] Point contribution and issue links in all retained repositories to
  `mdrideout/junjo`.

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

# Junjo monorepo migration remediation plan

## Status

Repository remediation was implemented, validated, and merged by pull request
12 at `02f34073ceb40963e716498cf2caaaddafa2db28` on 2026-07-13. The accepted ADRs,
Junjo-owned Base UI foundation, release transaction, deployment proof, CI
routing, secret scanning, license metadata, repository-owned validation, and
immutable workflow evidence are recorded in `MONOREPO_MIGRATION_RECORD.md`.

The final pull-request revision `3f8e5b3` passed Platform Gate and Gitleaks.
Credentials, trusted publishing, direct hosting reconfiguration, first
releases, and old repository retirement are the remaining operator work in
`MONOREPO_GITHUB_CUTOVER_RUNBOOK.md`.

No production tag, mirror publication, repository archival, or Cloudflare
source cutover may occur before its corresponding cutover gate passes.

## Objective

Finish the migration with evidence that is both complete and honest:

1. Current Junjo-authored source and artifacts are Apache-2.0, while
   third-party material retains its own license and notice.
2. Studio uses an independently authored, accessible UI foundation that Junjo
   can freely control, customize, and evolve without distributing Tailwind Plus
   component source as Junjo source.
3. A Studio release is a globally serialized, forward-only transaction whose
   images, distributions, mirrors, and GitHub release are cryptographically
   tied to one version and source revision.
4. Deployment tests exercise the actual setup behavior and prove that a real
   Junjo application can send telemetry that Studio can query.
5. CI routes every owning component and rejects secret, provenance, license,
   contract, and release-policy regressions.
6. Documentation distinguishes completed evidence from planned work.

## Accepted decisions

These decisions were accepted before implementation. They change strategy and
therefore live in ADRs rather than being inferred from code.

### 1. Current Studio UI foundation

Recommended decision:

- keep Tailwind CSS as Studio's styling engine;
- adopt Base UI as the default headless interaction layer;
- make Junjo own its visual design, layout, and thin semantic wrappers;
- use native HTML for links, text, tables, and non-interactive layout;
- prohibit copying or adapting Tailwind Plus source, component APIs, class
  recipes, or visual assets into the replacement.

This is a product-foundation decision, not merely a licensing cleanup. Studio's
interfaces will need more control and customization as the product evolves.
Junjo therefore needs to own the visual language, semantic component contracts,
composition, responsive behavior, and theming surface. Base UI supplies
well-tested interaction machinery without prescribing how Junjo looks or how
its features are assembled.

The first replacement should establish that ownership without prematurely
building a large design system:

- shared components expose small semantic contracts based on actual Studio
  needs, not a generic catalog of colors and variants;
- Base UI state attributes and primitive APIs remain encapsulated inside the
  Junjo UI layer rather than leaking into feature code;
- repeated visual decisions become Junjo-owned semantic theme variables next
  to the existing Tailwind `@theme` configuration;
- feature-specific presentation remains with the feature until repetition
  proves it belongs in the shared layer;
- future changes to branding, density, responsiveness, accessibility, or
  user-selectable appearance can be made in Junjo-owned code without replacing
  the interaction foundation.

Tailwind CSS is not the licensing problem. It is MIT-licensed and can remain.
The problem is the copied or derived Tailwind Plus Catalyst component source in
`apps/studio/frontend/src/components/catalyst`.

The standalone [Base UI project](https://base-ui.com/) is the intended
foundation—not the older MUI Base library. Base UI is suitable because it is
unstyled, MIT-licensed, compatible with React 19 and Tailwind, and supplies
accessible interaction, focus, keyboard, portal, and popup behavior. The
reviewed stable release is `@base-ui/react` 1.6.0. See the official [Base UI
quick start](https://base-ui.com/react/overview/quick-start), [project and
license description](https://base-ui.com/react/overview/about), and
[accessibility contract](https://base-ui.com/react/overview/accessibility).

### 2. Historical Catalyst source — resolved

Deleting Catalyst from `HEAD` fixes current source archives and future builds,
but does not remove Catalyst blobs from imported commits and tags.

Accepted decision:

- independently rewrite and remove Catalyst from the current tree;
- record the license holder's confirmed Tailwind UI/Plus purchase and Studio
  application end-product use;
- retain historical commits without claiming their Catalyst material is
  Apache-2.0;
- add an explicit third-party/provenance notice that applies to historical
  material;
- preserve the license confirmation with the migration evidence.

The license holder supplied that confirmation on 2026-07-13. Historical commits
and tags are intentionally retained under their applicable licenses. No history
rewrite is required, and the historical-source decision is not a remaining
cutover gate.

Changing Headless UI imports to Base UI while retaining Catalyst markup,
Tailwind class recipes, component structure, or visual assets does **not** fix
the issue. Tailwind Plus states that derivative components remain governed by
its license. See the official [Tailwind Plus license](https://tailwindcss.com/plus/license).

### 3. Studio release transaction

Recommended decision:

- `0.81.1` is the immutable pre-monorepo completed-release baseline;
- the first monorepo Studio release is `0.81.2` or greater;
- all Studio production releases share one concurrency group and never cancel
  an in-progress release;
- a lower or already-completed version fails before Docker, mirror, floating
  tag, or GitHub release mutation;
- an interrupted same-version run may resume only when immutable version and
  source-revision image tags match the expected digests;
- Docker Hub itself enforces immutability for stable `X.Y.Z` and full
  40-character source-SHA tags, while `major.minor`, `latest`, and run-scoped
  candidate tags remain mutable;
- the old Studio publisher is disabled before this monorepo is confirmed as
  the exclusive release authority;
- exact mirrors and image repositories are repository-owned data, not mutable
  workflow input;
- the GitHub release remains the final publication step and uses a dedicated
  protected environment.

### 4. Unmerged old Studio branch

The old Studio repository has an unmerged
`feat/node-exceptions-dashboard` branch at
`6d3171c1c41270ad5baa92ad361179bf60942118`, three commits ahead of its base.

Recommended decision: leave the unfinished branch readable in the archived
repository and create a monorepo issue describing it. Import it only if its
unfinished code is deliberately made part of the canonical product history.

### 5. Production setup boundary

Recommended decision: keep the migration's existing `.env` generation and
manual Caddy domain-editing boundary. Test that contract exactly. Expanding the
wizard into DNS, certificate, or Caddyfile automation is product work and is
outside this migration.

## Accepted ADRs and contract

The implementation is governed by these accepted decisions and its one small
machine-readable release contract:

1. `docs/adr/0002-platform-licensing-and-third-party-material.md`
   defines the Apache-2.0 boundary, third-party license preservation, current
   versus historical source treatment, and release notice requirements. After
   acceptance, update ADR 0001's licensing section to reference this decision.
2. `apps/studio/docs/adr/005-studio-frontend-interaction-foundation.md`
   defines Base UI as behavior, Tailwind CSS as styling machinery, Junjo as the
   visual-design and customization owner, native elements as the default where
   no headless primitive is required, and the boundary between shared semantic
   UI contracts and feature-owned presentation.
3. `apps/studio/docs/adr/006-studio-release-transaction.md` defines release
   states, ordering, serialization, immutability, resumability, evidence, and
   protected-environment boundaries.
4. `tooling/studio_release_contract.json` is the small machine-readable data
   contract consumed by release policy, mirror publishing, evidence building,
   and repository validation. It contains:
   - schema version;
   - completed pre-monorepo baseline `0.81.1`;
   - exact Docker Hub immutable-tag rules;
   - the exact backend, frontend, and ingestion Docker repositories;
   - `minimal -> mdrideout/junjo-ai-studio-minimal-build:master`;
   - `vm-caddy -> mdrideout/junjo-ai-studio-deployment-example:master`.

The JSON file contains release identity data only. Release behavior remains in
small, directly tested policy and publication scripts.

## Workstream A: restore documentation truth

Do this first so subsequent work is not guided by false completion claims.

### Changes

- Change `MONOREPO_MIGRATION_PLAN.md` from "repository implementation
  complete" to "source consolidation complete; remediation in progress" and
  link this plan.
- Mark the validation section of `MONOREPO_MIGRATION_RECORD.md` as provisional.
  Keep the commands and counts that genuinely ran, but withdraw claims of full
  setup-wizard, VM image, end-to-end telemetry, release dry-run, and production
  readiness proof.
- Restore every external Gate A and Gate B item in
  `MONOREPO_GITHUB_CUTOVER_RUNBOOK.md` to unchecked unless an exact run,
  settings snapshot, digest, commit, or deployment URL is recorded.
- Record the current control-plane facts without implying completion:
  - branch protection requires `required` and `Gitleaks Scan`;
  - `pypi`, `studio-dockerhub-production`,
    `studio-distributions-production`, and `studio-release-production`
    environments exist;
  - mirror destinations are fixed by the repository-owned release contract;
  - Docker Hub and GitHub App credentials have not been populated;
  - pull request 12's repository-owned checks passed at the reviewed revision,
    while its Cloudflare check failed;
  - the old Studio repository and its workflows remain active.
- Add the omitted `feat/node-exceptions-dashboard` branch to migration
  provenance and record its accepted disposition.
- Correct Agent-roadmap paths that still assume the old root layout and remove
  obsolete separate-repository wording.

### Completion gate

Every statement phrased as completed has an adjacent exact revision, run,
artifact, or validation result. Planned work is a checkbox, not evidence.

## Workstream B: replace Catalyst with a Junjo-owned, customizable UI foundation

### Existing footprint

The reviewed `components/catalyst` directory contains nine files and 983 lines:

- `button.tsx`
- `dialog.tsx`
- `link.tsx`
- `navbar.tsx`
- `sidebar-layout.tsx`
- `sidebar-menu.tsx`
- `sidebar.tsx`
- `switch.tsx`
- `text.tsx`

The runtime surface is much smaller than those generic components suggest:

- six controlled dialogs;
- two Catalyst switch call sites;
- action buttons using only default and quiet/plain appearances;
- the application shell, desktop navigation, and mobile sidebar;
- no application use of the Catalyst Button-as-link API;
- no live use of the Catalyst current-item animation;
- duplicated nested `nav` markup in the present shell;
- switches without programmatically associated labels.

`@headlessui/react` and `framer-motion` are used only by this Catalyst tree.
The frontend also has one active Radix Switch through the `radix-ui` package;
it should move to the same Junjo Switch during this work so Studio has one
switch contract. Active Radix Select and icon usage are unrelated and remain.

### Target responsibility boundaries

| Layer | Owns | Must not own |
| --- | --- | --- |
| Base UI | ARIA mechanics, focus, keyboard interaction, portals, dismissal | Junjo appearance, application state, routing |
| Tailwind CSS | Utility-based styling mechanism | component semantics or proprietary component recipes |
| Junjo UI | original visual language, semantic theme surface, and thin semantic wrappers | feature/domain state |
| Feature | controlled state, submission, routing decisions | focus-trap or popup machinery |

### Target source shape

Use names based on semantics rather than preserving Catalyst's API:

- `components/actions/action-button.tsx`: Base UI Button for actions with the
  primary, secondary, and destructive intents used by Studio;
- `components/overlays/modal.tsx`: Base UI Dialog composition with controlled
  `open`/`onOpenChange`, explicit sizes, title, description, close, and action
  slots;
- `components/forms/switch.tsx`: Base UI `Switch.Root` and `Switch.Thumb` with an
  explicit accessible-label contract;
- `components/navigation/app-link.tsx`: React Router Link for internal routes
  and native anchors for external destinations;
- `components/layout/app-shell.tsx`: native semantic desktop layout and a
  positioned Base UI Dialog for mobile navigation;
- native headings, paragraphs, strong text, code, `nav`, `aside`, and `main`
  unless repetition proves a helper is needed.

Do not create a compatibility copy of Catalyst under a new folder.

The shared layer is an ownership boundary, not an attempt to predict every
future interface. Its public props should describe product semantics such as an
action's intent or a modal's size. Base UI implementation details, state
attributes, and styling mechanics stay private to that layer so Junjo can
change them without rewriting feature code.

### Implementation sequence

1. Record the before-change component footprint and production bundle output as
   migration evidence. Use the interaction requirements below—not Catalyst
   screenshots, markup, or styling—as the replacement contract.
2. Add `@base-ui/react` 1.6.0 through the frontend package manager and preserve
   its MIT notice in the third-party notice file. Import component subpaths,
   such as `@base-ui/react/dialog`, rather than the package barrel.
3. Add `#root { isolation: isolate; }` for portal stacking and
   `body { position: relative; }` for the documented mobile backdrop behavior.
4. Add only the shared semantic visual variables required by the replacement
   alongside the existing Tailwind `@theme` configuration in
   `src/css/index.css`. Do not recreate Catalyst's palette or introduce an
   exhaustive speculative token system.
5. Implement the original action button and app-link contracts. Buttons remain
   buttons; links remain links.
6. Implement the modal contract with Base UI `Root`, `Portal`, `Backdrop`,
   `Viewport`, `Popup`, `Title`, `Description`, and `Close`. Replace Headless UI
   transition state with Base UI `data-starting-style` and
   `data-ending-style` transitions.
7. Migrate these six consumers directly; do not keep an `onClose` adapter:
   - `features/users/CreateUserDialog.tsx`;
   - `features/api-keys/CreateApiKeyDialog.tsx`;
   - `features/prompt-playground/components/GenerationSettingsModal.tsx`;
   - `features/prompt-playground/components/ModelSelectorModal.tsx`;
   - `features/prompt-playground/components/ProviderWarningModal.tsx`;
   - `features/prompt-playground/components/JsonSchemaModal.tsx`.
8. Implement the Junjo Switch, migrate the two Catalyst consumers and the one
   existing Radix Switch consumer, use `onCheckedChange`, and add associated
   labels.
9. Replace `AppLayout.tsx` and the Catalyst sidebar composition with semantic
   Junjo layout. Use a positioned Dialog for mobile navigation, explicitly
   close it after route selection, display the active route, remove the nested
   `nav`, and replace placeholder mobile content.
10. Delete the entire `components/catalyst` directory.
11. Remove `@headlessui/react`, `framer-motion`, the unused direct
    `@radix-ui/react-switch`, and the `radix-ui` meta-package after verifying no
    remaining import. Keep `@radix-ui/react-select` and icons until a separate
    consolidation decision.
12. Add `apps/studio/THIRD_PARTY_NOTICES.md` as Studio's canonical notice file,
    include it in Studio source and published artifacts, and ensure Base UI's
    MIT license is represented. Apply the accepted historical Catalyst decision
    without describing third-party source as Apache-2.0.

Base UI composition uses a `render` prop rather than Headless UI's `as`
contract. Any custom component passed to `render` must forward its ref and
spread received props. See the official [composition
guidance](https://base-ui.com/react/handbook/composition). Base UI animation
states are documented in its [animation handbook](https://base-ui.com/react/handbook/animation).

### Deterministic tests

Add React Testing Library and `user-event` coverage for:

- modal accessible title and description;
- initial focus, Tab and Shift+Tab containment, Escape dismissal, pointer
  dismissal policy, visible close action, and focus restoration;
- form submission, disabled buttons, and explicit submit-button behavior;
- switch label, mouse, Space key, disabled state, controlled state, and callback;
- internal Router links versus external anchors;
- mobile sidebar open, close, Escape, focus return, and close-on-route;
- auth-dependent menu visibility and active-route state;
- desktop/mobile shell semantics, auth-dependent visibility, active-route
  state, and mobile navigation behavior.

Portal assertions query the document body. Add browser shims only when a
specific Base UI behavior requires them.

### Validation and acceptance

Run from `apps/studio/frontend`:

- `npm ci`
- `npm run lint`
- `npm run test:run`
- `npm run build`
- production bundle analysis before and after

Then run `apps/studio/run-all-tests.sh` and build the frontend production image.

The workstream is complete only when:

- `rg` finds no Catalyst import or current-source implementation;
- no Catalyst class recipe, proprietary asset, or compatibility API was carried
  into the new components;
- `@headlessui/react`, `framer-motion`, `@radix-ui/react-switch`, and
  `radix-ui` are absent from the lock and manifest when unused;
- every dialog, switch, link, and mobile-navigation behavior above passes;
- keyboard interaction plus accessible-name and ARIA relationship assertions
  pass;
- features depend on Junjo's semantic component contracts rather than Base UI
  state attributes or primitive-specific APIs;
- a shared appearance change can be made in Junjo-owned theme and component
  styles without changing interaction behavior or feature state;
- release archives contain only the new UI source and the required notices;
- bundle deltas are recorded and reviewed rather than assumed.

### Does this fix the licensing issue?

| Outcome | Full original rewrite and deletion | Primitive-only swap |
| --- | --- | --- |
| Current source is Junjo-owned Apache-2.0 | Yes | No |
| Base UI behavior can ship with Junjo | Yes, with MIT notice | Yes, but Catalyst-derived source remains |
| Tailwind CSS can remain | Yes | Yes |
| Future source archives omit Catalyst | Yes | No |
| Historical Git blobs disappear | No; intentionally retained under the confirmed license | No |

The recommended rewrite fixes the current-tree and future-release problem. The
historical-source decision is resolved and recorded in ADR 0002.

## Workstream C: make Studio releases one explicit transaction

### Policy and preflight

- Add the release ADR and `tooling/studio_release_contract.json`.
- Add a small, pure, unit-tested release-policy script. It determines whether a
  request is `new`, a valid partial `resume`, `completed`, or `stale`.
- Resolve every production run to the constant concurrency group
  `studio-release`; keep `cancel-in-progress: false`. Give non-publishing
  rehearsals run-scoped concurrency so they cannot interfere with production.
- In the `prepare` job, before any production environment or mutation:
  - validate `studio-v<apps/studio/VERSION>`;
  - fetch `master` and all `studio-v*` tags;
  - require the source commit to be reachable from `master`;
  - bind the fetched release-tag target to the event source revision;
  - reject a production version at or below the `0.81.1` baseline;
  - reject any version lower than an already-seen higher Studio tag;
  - classify an existing GitHub release as `completed` and every invalid
    identity as `stale` before mutation.
- After candidate image construction, classify an empty immutable-tag set as
  `new`, matching partial version/source-SHA tags as `resume`, and any digest
  conflict as `stale`. Only `new` and `resume` proceed.
- Before any registry mutation, require the protected control-plane assertion
  that this monorepo is the exclusive Studio publisher and validate the live
  immutable-tag settings of all three Docker Hub repositories against the
  release contract.
- Revalidate both source reachability and the live release-tag target before
  final GitHub release creation.
- Keep manual and pull-request dry-runs capable of validating the checked-out
  current version without credentials or mutation.

Acceptance scenarios include simultaneous `0.81.2` and `0.81.3`, a queued
lower version after a higher version completes, a completed-release rerun, and
an interrupted same-version resume. Only the valid partial resume proceeds.

### Bind distribution identity

- Make `publish_studio_distribution.py` accept a distribution identity, load
  the release contract, and reject an unexpected repository, branch, or
  manifest identity before authentication or clone.
- Validate both contract-owned mirror identities and default branches together
  before minting a GitHub App token, revalidate both with the installation
  token before either push, and keep the per-publisher recheck.
- Make `build_studio_release_evidence.py` require the exact expected mirror
  repository and branch as well as source revision, commit, and tree.
- Add tests proving swapped targets, wrong branch, wrong distribution, and
  missing target fail before a publication command runs.

### Bind image identity

- Replace loose candidate-digest files with per-service JSON evidence containing
  repository, candidate digest, version tag and digest, and source-SHA tag and
  digest.
- Re-inspect immutable version and source-SHA tags after creation and again in
  the final release job.
- Require all three digests to be equal and require exact repository and tag
  names in the evidence builder.
- Give each producer one stable artifact name within the workflow run and use
  producer-owned overwrite on rerun.
- Record the admitted workflow attempt and make every production job reject a
  different current attempt. This makes "Re-run failed jobs" fail closed rather
  than reuse stale admission or registry-control decisions. Require operators
  to use "Re-run all jobs", which refreshes controls and producer-owned evidence
  without selecting artifacts from another workflow run.

### Publication boundary

- Add `studio-release-production`, with no secrets and only `studio-v*` tags
  allowed, to the final GitHub release job.
- Keep Docker credentials only in `studio-dockerhub-production`.
- Keep `STUDIO_RELEASE_AUTHORITY_CUTOVER` in that protected environment unset
  until the old publisher and Docker Hub autobuilds are disabled; then set it
  to the exact monorepo repository identity.
- Keep mirror credentials only in `studio-distributions-production`.
- Preserve ordering: immutable images, exact-image smoke, immutable mirrors,
  floating tags, Docker descriptions, final evidence, GitHub release.
- If a rebuild produces a different digest, do not overwrite immutable tags;
  make a corrective version.

### Completion gate

Offline tests and repository invariants prove serialization, forward-only
versioning, exact repo/branch/digest binding, rerun-safe same-run artifacts, valid
resume behavior, and final protected environment use. A dry-run performs no
registry, mirror, floating-tag, or GitHub-release mutation.

## Workstream D: prove deployment behavior

### Black-box setup-wizard tests

Add `tooling/tests/test_studio_setup_wizards.py` or an equivalently explicit
black-box suite. Run each wizard from a temporary copied distribution rather
than refactoring the duplicated operator CLIs into a hidden shared runtime.

Cover the root Studio wizard and both distribution wizards:

- development and production modes;
- all required arguments and exact generated profile, environment, and URLs;
- secrets that decode to the required 32 bytes;
- no secret or Cloudflare token in stdout/stderr;
- missing or invalid hostname/token failure;
- dry-run produces no file change;
- a second run preserves secrets and creates `.env.bak` byte-equal to the prior
  `.env`;
- `--force-secrets` rotates secrets;
- `.env`, `.env.bak`, and the atomic writer's explicitly named private staging
  pattern remain ignored and absent from exports; interruption residue never
  becomes a Git candidate.

Keep `validate_studio_deployments.py` focused on static and Compose contracts.
Do not call a compile/help check "full setup-wizard validation."

### Images and end-to-end telemetry

- In deployment CI, build the VM/Caddy distribution's Caddy and `junjo_app`
  images in addition to the three Studio images.
- Add one explicit smoke runner with deterministic cleanup:
  1. create a unique Compose project and temporary runtime root;
  2. run development setup;
  3. start the exact locally built or released Studio images;
  4. wait for service health;
  5. create the first Studio user and API key using a cookie jar;
  6. inject the key and start the example Junjo application;
  7. poll Studio's service and workflow APIs until the real example workflow is
     queryable;
  8. always run `compose down --volumes`;
  9. emit container logs only on failure and never print credentials.
- Treat production Caddy/TLS as configuration validation because manual domain
  editing remains the accepted boundary.

For pull requests and manual dry-runs, build local Linux/AMD64 Studio images
with the current exact version tags and do not pull a not-yet-published version.
For a production release, pull and re-inspect the exact registry manifests.

### Completion gate

Both distributions render, both setup wizards pass behavioral tests, both VM
images build, a real example workflow reaches Studio and is queryable, cleanup
is deterministic, and the exact release-image smoke repeats from registry
digests in production.

## Workstream E: close CI, security, and metadata gaps

### Path routing

Extend `detect_ci_changes.py`, its tests, and workflow path ownership so:

- `apps/studio/.dockerignore` routes backend, frontend, and deployment builds;
- `apps/studio/compose.yaml`, `compose.monitoring.yaml`, `.env.example`, and the
  root setup script route deployments and the affected Studio owners;
- `apps/studio/e2e_test_apps/**` routes deployments and telemetry;
- any unmapped Studio product path fails the routing invariant rather than
  silently skipping validation.

### Secret scanning

- Remove broad Gitleaks exceptions for test Python files, workflows, and generic
  credential-looking regular expressions.
- Replace fixture-looking secrets with obvious low-entropy test placeholders
  where possible.
- Keep only fingerprint-scoped exceptions for unavoidable historical findings.
- Prove a full-history scan passes and a newly introduced high-entropy value in
  a test or workflow fails.

### License and artifact metadata

- Add Apache-2.0 SPDX metadata to Junjo-authored backend, ingestion, frontend,
  website, and package artifacts.
- Add OCI source and `org.opencontainers.image.licenses=Apache-2.0` labels to
  all Junjo-authored Studio and distribution Dockerfiles.
- Add and validate `apps/studio/THIRD_PARTY_NOTICES.md`; third-party libraries
  retain MIT or other applicable licenses.
- Restore the platform-wide Apache completion claim only after the Catalyst
  current-tree replacement and historical provenance decision are implemented.

### Workflow integrity

- Extend `validate_repository.py` and tooling tests to require the new ADRs,
  release contract, global concurrency, baseline guard, exact mirror targets,
  attempt-scoped artifacts, exact tag evidence, final environment, and package
  metadata.
- Validate immutable action pins in both `.yml` and `.yaml` files.
- Keep privileged actions SHA-pinned.
- After merge, enable GitHub's action-SHA enforcement and record the settings
  snapshot.
- Add an immutable `studio-v*` tag ruleset if GitHub supports the required
  repository policy, and record the result.

## Workstream F: final validation and cutover

### Gate A: pull request evidence

Run and record, in dependency order:

1. offline tooling and repository-invariant tests;
2. strict full-history Gitleaks;
3. setup-wizard black-box tests;
4. Compose, export, archive reproducibility, and mirror equivalence tests;
5. local Studio, Caddy, and example-app image builds;
6. end-to-end telemetry smoke;
7. actionlint and Zizmor;
8. the full Studio suite;
9. website locked install, checks, links, and build;
10. Python Ruff, pytest, ty, Sphinx, package build, and Twine validation;
11. telemetry contract compatibility plus producer and consumer conformance;
12. a no-credential Studio release dry-run;
13. merge the exact validated revision with a merge commit so imported history
    remains in `master` ancestry.

The read-only release-validation workflow is reusable through `workflow_call`;
both the top-level publisher and platform gate invoke it. Production and
pull-request dry-runs therefore share the same repository-owned admission,
validation, and build jobs without maintaining a weaker approximation. The
publisher itself is not reusable because its finalizer has job-scoped
`contents: write`; this keeps write capability out of the pull-request workflow
graph. When deployment or release ownership is affected, validation is the
umbrella: the gate skips its direct Studio, telemetry, and deployment calls so
those checks execute once. Component-only changes continue to use the smaller
direct jobs.

### Gate B: post-merge production control-plane configuration

- Merge immediately after Gate A is green, then configure production authority.
- Verify the already-created, tag-restricted `studio-release-production`
  environment before using it.
- Populate least-privilege Docker Hub and GitHub App credentials in their
  owning environments.
- Docker Hub Autobuilds are already confirmed disabled. Disable every old
  Studio release workflow, configure the contract-owned immutable-tag rules on
  all three existing `mdrideout` image repositories, and only then set
  `STUDIO_RELEASE_AUTHORITY_CUTOVER=mdrideout/junjo` in
  `studio-dockerhub-production`.
- Configure PyPI Trusted Publishing for the moved workflow.
- Configure the accepted immutable release-tag ruleset.

### Gate C: direct external cutover and first production releases

- Verify `master` repeats the required repository checks.
- Enable repository action-SHA enforcement only after the merged workflow set
  is present, then record the settings response.
- Release the next Python version according to the Python release plan.
- Prepare Studio `0.81.2` or later; never reuse `0.81.1`.
- Apply the monorepo Cloudflare settings after merge:
  - edit the existing Python docs project because it already uses
    `mdrideout/junjo`, with source `sdks/python` and output
    `docs/_build/html`;
  - delete/recreate the website Pages project from `mdrideout/junjo` because
    Cloudflare cannot change the connected repository on an existing
    Git-integrated project, with source `apps/website` and output `dist`.
- Verify exact image digests, source-SHA tags, distribution archives, mirror
  repository/branch/commit/tree, release evidence, and GitHub release assets.
- Verify the deployed website and Python docs from their canonical monorepo
  sources.

### Gate D: old repository retirement

Only after replacement production surfaces pass:

- disable old Studio workflows;
- convert both deployment repositories to generated mirrors;
- publish destination notices;
- archive the old Studio and website repositories;
- retain the unfinished branch according to its accepted disposition;
- update the migration record with exact final evidence.

## Parallelization and ordering

After the ADRs are accepted, these implementation tracks can run in parallel:

- Catalyst/Base UI replacement;
- release transaction and evidence;
- setup-wizard and deployment smoke tests;
- CI routing, Gitleaks, and metadata corrections.

They converge before Gate A. External credentials, Cloudflare production
cutover, publishing, and repository archival remain strictly after merge.

```text
documentation truth
        |
accepted ADRs and release contract
        |
        +--> original Junjo UI replacement --------+
        +--> release transaction and evidence -----+--> Gate A --> merge
        +--> setup and telemetry proof ------------+              |
        +--> CI, security, and metadata ------------+              v
                                                        credentials/cutover
                                                                  |
                                                                  v
                                                        archive old sources
```

## Definition of done

The monorepo migration is complete only when:

- accepted ADRs match the implementation;
- the current tree contains no Catalyst-derived implementation;
- historical Catalyst treatment and the license holder's purchase confirmation
  are recorded while the imported history retains its applicable licenses;
- current Junjo source and artifacts truthfully identify as Apache-2.0 and
  third-party notices remain intact;
- every release target is fixed by the release contract and evidenced by exact
  digest, repository, branch, commit, and tree;
- a real example application sends telemetry that the released Studio can
  query;
- all repository-owned checks pass on the merge revision and the directly
  reconfigured Cloudflare production projects deploy from `master`;
- the first monorepo releases succeed from protected environments;
- old repositories no longer act as competing source or release authorities;
- `MONOREPO_MIGRATION_RECORD.md` contains the exact proof for every completed
  claim.

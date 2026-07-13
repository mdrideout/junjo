# ADR-006: Studio release transaction

## Status

Accepted

## Context

A Studio release changes several independently hosted surfaces: three Docker
repositories, two generated deployment mirrors, and one GitHub release. Those
changes cannot be committed atomically by the hosting providers. Release
automation therefore needs an explicit ordering and enough evidence to prove
that every surface represents one source revision.

Per-tag workflow concurrency is insufficient. Two different versions could run
at once and the older run could finish last, moving floating image tags and
deployment mirrors backwards. Mutable repository variables are also an unsafe
way to select publication destinations because evidence cannot distinguish the
intended mirror from an arbitrary repository supplied at run time.

Studio `0.81.1` is the final completed release from before the monorepo. It is
an immutable baseline, not a version that monorepo automation may rebuild.
Five earlier imported tags use the old two-part form: `studio-v0.10`,
`studio-v0.20`, `studio-v0.30`, `studio-v0.40`, and `studio-v0.42`. They are
historical provenance, not members of the canonical three-part release stream.

## Decision

Treat each production Studio release as one globally serialized, forward-only
transaction.

### Identity and admission

- All production runs use the constant `studio-release` concurrency group and
  do not cancel an in-progress run. Manual non-publishing rehearsals use
  run-scoped concurrency and cannot queue ahead of or displace a production
  transaction. Pull-request validation is read-only and needs no release
  concurrency group.
- The candidate is a stable semantic version greater than `0.81.1`, every
  completed Studio GitHub release, and every other canonical three-part
  `studio-v*` Git tag. The five exact imported two-part tags are enumerated in
  the release contract; any unrecognized two-part tag fails admission. This
  prevents a queued older run from starting after a newer tag was created.
- The release tag is exactly `studio-v<version>`.
- A production tag must identify a commit reachable from `master` and the
  checked `apps/studio/VERSION` value. Its fetched target must equal the event
  source revision at admission and again immediately before finalization.
- An existing GitHub release with the candidate tag, including a draft, blocks
  the run before any registry or mirror mutation.
- A workflow-dispatch or pull-request workflow-call run is a non-publishing
  rehearsal. It validates its checked-out version and release policy, runs the
  same component validations and image builds, and may run from a branch.

### Repository-owned publication contract

`tooling/studio_release_contract.json` is the machine-readable owner of:

- the completed pre-monorepo baseline;
- the exact imported two-part historical Studio tags;
- the exact repository for each Studio service image;
- the exact Docker Hub immutable-tag rules for stable versions and full source
  revisions;
- each distribution's canonical source path, mirror repository, and branch.

Release scripts accept a service or distribution identity and derive its
destination from this contract. They do not accept arbitrary publication
destinations. Mirror publication also rejects repository redirects whose
resolved `nameWithOwner` differs from the contract. A contract change is a
reviewed release-architecture change.

### Ordered production states

The transaction advances in this order:

1. **Admitted**: validate identity, reachability from `master`, the live tag
   target, prior releases, and the publication contract without production
   credentials.
2. **Validated**: all Studio, telemetry, and distribution checks pass.
3. **Registry controls proven**: the protected environment confirms this
   monorepo is the exclusive release authority, and live Docker Hub settings
   prove that stable `X.Y.Z` and full 40-character source-SHA tags are immutable
   while floating tags remain mutable.
4. **Candidate images built**: architecture images are pushed by digest and
   combined into run-scoped candidate manifests.
5. **Immutable images published**: every service's version and full source-SHA
   tag is absent or already has the candidate digest, then both tags are
   published under registry-enforced immutable rules and reinspected.
6. **Exact images smoked**: deployment validation runs against those registry
   images.
7. **Distribution destinations proven**: both contract-owned mirror identities
   and default branches are resolved together before minting the installation
   token and again before either mirror is mutated.
8. **Distributions published**: generated trees are pushed to their exact
   contract-owned mirrors and fresh clones prove tree equality.
9. **Floating tags promoted**: `<major>.<minor>` and `latest` move to the exact
   version digest.
10. **Evidence finalized**: every immutable image tag is reinspected and all
   archive, source, tree, repository, branch, commit, and digest bindings are
   validated.
11. **GitHub release published**: the release is created last through the
   `studio-release-production` protected environment.

No later state may begin unless all preceding states succeeded.

### Interruption and retry

Docker Hub's repository-side immutable-tag rules make version and full
source-SHA tags write-once even if another writer races the workflow. A retry of an
interrupted candidate is allowed only when every pre-existing immutable tag
has the newly built candidate digest. Any mismatch fails rather than
overwriting the tag. Generated mirror publication is idempotent because the
exported tree is deterministic; an identical tree creates no commit.

The policy names the observable states explicitly. A candidate with no prior
immutable state is `new`; matching partial immutable tags make it `resume`; a
completed GitHub release is `completed`; and an older version, an unreachable
source revision, an unexpected tag, a draft release, or a digest conflict is
`stale`. Only `new` and `resume` can proceed. Advancing `master` does not break a
retry while the tagged source remains reachable, but a newer stable Studio tag
makes the older transaction stale and requires a corrective next version.

A completed GitHub release is terminal. Rebuilding a completed version or
rolling an older version forward is prohibited. If released bytes must change,
publish a new version.

Evidence artifact names are stable within one workflow run. Each producing job
owns one artifact name and uploads with overwrite enabled. Production jobs also
require the workflow attempt recorded by `prepare` to equal their current
attempt. GitHub's "Re-run failed jobs" operation is therefore rejected because
it would reuse admission and live-control decisions from an earlier attempt.
Operators must choose "Re-run all jobs", which refreshes admission and registry
controls and atomically replaces each producer's same-run artifact. Artifacts
from a different workflow run are never selected.

### Evidence

Release evidence records, for each image:

- service and exact repository;
- Studio version and full source revision;
- exact multi-platform digest;
- version tag and source-SHA tag with their independently inspected digests.

For each distribution it records:

- distribution and canonical source path;
- exact mirror repository and branch;
- archive hash, generated-tree hash, and verified mirror commit;
- source repository, revision, Studio version, and compatible SDK version.

Evidence construction fails on missing, extra, or contradictory identity
fields. A digest captured only from a build step is not final evidence; the
published immutable tags are inspected again immediately before the GitHub
release.

### Credential boundaries

- `.github/workflows/studio-release-validation.yml` is the single reusable
  admission, test, deployment, and dry-build layer. It has only
  `contents: read` and is called by both the pull-request gate and publisher.
- `.github/workflows/studio-docker-publish.yml` is not reusable. This prevents
  its write-capable finalizer from entering a read-only pull-request workflow
  graph.
- Docker mutation uses `studio-dockerhub-production`.
- `studio-dockerhub-production` must define
  `STUDIO_RELEASE_AUTHORITY_CUTOVER=mdrideout/junjo` only after every old Studio
  publisher and Docker Hub autobuild is disabled. The registry-control job
  checks that assertion and live Docker Hub immutable-tag settings before the
  first image mutation.
- Mirror mutation uses `studio-distributions-production`.
- Final GitHub release mutation uses `studio-release-production` with
  job-scoped `contents: write`.
- Admission, tests, dry builds, and evidence validation do not receive
  production credentials.

## Consequences

- Different Studio versions cannot publish concurrently.
- An old or stale run cannot roll floating tags or generated mirrors backwards.
- Release destinations are explicit and reviewable.
- Interrupted transactions can retry through "Re-run all jobs" without
  weakening immutable tags.
- Partial failed-jobs reruns fail closed instead of reusing stale admission or
  live-control decisions.
- Full-workflow reruns preserve exact same-run evidence.
- Pull requests that affect deployment/release ownership gate on the same
  no-credential release rehearsal used by manual validation.
- The first monorepo Studio release must be `0.81.2` or greater.
- Correcting released artifacts always requires a new version.

## Alternatives rejected

- Per-version concurrency does not protect shared floating tags or mirrors.
- Overwriting immutable tags makes evidence unverifiable.
- Supplying destinations through repository variables weakens the publication
  contract and allows evidence for the wrong repository.
- Publishing a draft GitHub release first creates a visible release object
  before its artifacts are proven and complicates retry semantics.
- Compatibility paths for the pre-monorepo publisher would preserve two release
  authorities and are intentionally not provided.

## Related

- `tooling/studio_release_contract.json`
- `.github/workflows/studio-release-validation.yml`
- `.github/workflows/studio-docker-publish.yml`
- `tooling/scripts/validate_studio_release_policy.py`
- `tooling/scripts/build_studio_release_evidence.py`
- `tooling/scripts/publish_studio_distribution.py`

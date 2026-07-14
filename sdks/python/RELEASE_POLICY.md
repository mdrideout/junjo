# Release Policy

## Branch Policy

- `master` is the release branch.
- Release tags and GitHub releases must point to commits that are on `master`.
- PyPI publishing happens from GitHub release publication only. Manual publish dispatch is not part of the release flow.

## Required Release Checks

Junjo requires Python 3.11 or newer. Python 3.13 is the repository-owned
development, documentation, and release-build version. Every release must pass
the Python SDK primary library-health checks from `sdks/python` on Python 3.13:

- `uv run ruff check .`
- `uv run pytest -q`
- `uv run ty check --error-on-warning src`
- `uv run sphinx-build -W -b html docs docs/_build/html`
- `uv run python -m build`
- `uv run twine check dist/*`

Compatibility jobs also run `uv run pytest -q` on Python 3.11, 3.12, and
3.14. PyPI publication waits for the primary health job, the complete supported
Python compatibility matrix, and a single Python 3.13 distribution build.

Keep `requires-python = ">=3.11"` and Ruff's `target-version = "py311"` aligned
with the minimum supported version. The development default must not allow
syntax that prevents installation on a declared compatible Python version.
Reassess the minimum when Python 3.11 reaches end of life in October 2027.

These checks define the required support contract for the `junjo` Python
library itself.

## Examples

- `examples/ai_chat` is the canonical Agent and Workflow composition acceptance
  application. Changes to that example, the Agent runtime it exercises, or its
  workspace inputs trigger its path-scoped backend and frontend checks.
- The AI Chat gate runs all nine deterministic scenarios, backend lint and type
  checks, and frontend tests, lint, and production build. It uses no provider
  credentials and is not a required check for unrelated pull requests.
- Other example applications remain best-effort references with manual smoke
  validation.
- Example health supplements; it never replaces the Python SDK library-health
  checks.

## Changelog

- Record major public behavior and breaking changes in `CHANGELOG.md`.
- Keep the newest changes at the top under `FUTURE RELEASE` until the next version is cut.
- Separate notes by:
  - `Breaking Changes`
  - `Library`
  - `Telemetry`
  - `Docs and Examples`
  - `Tooling and CI`

## Docs And Examples Discipline

When public behavior changes, keep these surfaces aligned:

1. runtime code
2. tests
3. public docstrings
4. Sphinx docs
5. examples

Release-ready code should not leave public docs or examples teaching stale behavior.

## Cross-Component Release Sequencing

Junjo SDK and Junjo AI Studio releases pair around the explicit contract under
`contracts/telemetry`. The deployment sources under `apps/studio/deployments`
are the canonical record of the supported SDK and Studio pair. The standalone
deployment repositories are generated mirrors and must not be updated
manually.

For an ordinary SDK release that does not change the shared contract, use the
normal SDK release flow above. For an intentional breaking telemetry-contract
release, source compatibility still merges atomically, but independently
versioned artifacts are cut in a deliberate producer-first sequence. A
temporary semantic-telemetry outage is accepted during this greenfield
cutover; there is no dual-version compatibility mode:

1. Merge the atomic contract, canonical fixtures, producer conformance tests,
   and strict consumer implementation.
2. Cut and publish the new `junjo` SDK through GitHub release publication.
   Contract-aware Studio diagnostics may be unavailable until the matching
   Studio release is deployed; raw telemetry availability is not a compatibility
   guarantee.
3. Prepare the matching Studio release only after that SDK is publicly
   installable. Update every canonical deployment SDK pin and compatibility
   statement, then validate ingestion, backend, frontend, exact images, and
   generated distributions against the published pair.
4. Publish Studio images and the generated deployment mirrors in one Studio
   release transaction. Upgrade other emitters after that cutover; old emitters
   are retired rather than retained behind fallbacks.
5. Deploy documentation last so public guidance describes the released pair.

For telemetry contract version 2, the producer release is `junjo` `0.65.0` and
the first matching Studio release must be `0.82.0` or newer. Release preparation
updates the VM/Caddy example pin and both deployment compatibility statements
from their currently released pair to those versions. The Agent implementation
branch does not pre-pin an SDK version that PyPI cannot yet install.

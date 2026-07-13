# Release Policy

## Branch Policy

- `master` is the release branch.
- Release tags and GitHub releases must point to commits that are on `master`.
- PyPI publishing happens from GitHub release publication only. Manual publish dispatch is not part of the release flow.

## Required Release Checks

Every release must pass the Python SDK library-health checks from
`sdks/python`:

- `uv run ruff check .`
- `uv run pytest -q`
- `uv run ty check --error-on-warning src`
- `uv run python -m build`
- `uv run twine check dist/*`

These checks define the required support contract for the `junjo` Python library itself.

## Examples

- Example applications under `sdks/python/examples` are best-effort reference apps.
- Example smoke validation is manual and non-blocking.
- Example health does not replace the required Python SDK library-health checks.

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
`contracts/telemetry`. Release in this order:

1. Cut the `junjo` SDK version and finalize `CHANGELOG.md`.
2. Release Junjo AI Studio (version bump + Docker Hub images) with the matching contract.
3. Update the `junjo-ai-studio-minimal-build` and `junjo-ai-studio-deployment-example` template repositories.
4. Publish `junjo` to PyPI via GitHub release publication.
5. Deploy the docs site last. Docs describe the paired releases, and the docs deploy is not wired to the release workflow.

# Junjo Platform

Junjo is a platform for building observable AI applications whose deterministic
workflows, autonomous behavior, and diagnostic tooling evolve through explicit
contracts.

This repository contains independently built and independently versioned
components:

- [`sdks/python`](sdks/python) — the `junjo` Python SDK and its examples and
  public Sphinx documentation.
- [`apps/studio`](apps/studio) — Junjo AI Studio's backend, frontend, ingestion
  service, canonical deployment distributions, and service documentation.
- [`apps/website`](apps/website) — the Junjo product and documentation website.
- [`apps/studio/deployments`](apps/studio/deployments) — canonical source for
  the minimal and VM/Caddy Studio distributions. Their standalone GitHub
  repositories are generated one-way release mirrors, not separate sources of
  truth.
- [`contracts/telemetry`](contracts/telemetry) — language-independent telemetry
  schemas and conformance fixtures shared by SDK emitters and Studio consumers.
- [`docs/roadmaps`](docs/roadmaps) — cross-platform product and implementation
  roadmaps.
- [`docs/adr`](docs/adr) — architectural decisions that cross component or
  language boundaries.

The monorepo is an integration boundary, not a runtime dependency. The Python
SDK does not depend on Studio, Studio does not import an SDK implementation,
and every component retains its own dependency lock, build, version, and
release artifact.

## Development entrypoints

Run commands from the component that owns them:

```bash
# Python SDK
cd sdks/python
uv sync --frozen --package junjo --extra dev
uv run ruff check .
uv run pytest -q
uv run ty check --error-on-warning src
uv run sphinx-build -b html docs docs/_build/html
cd ../..

# Studio
cd apps/studio
./run-all-tests.sh
cd ../..

# Shared telemetry contract
python3 contracts/telemetry/compatibility/generate_v2_fixtures.py
python3 contracts/telemetry/compatibility/validate_contract.py
git diff --exit-code -- contracts/telemetry

# Fast platform layout and release-routing invariants
python3 tooling/scripts/validate_repository.py
```

Live cross-layer validation uses a disposable local Studio instance. From the
repository root, run the provider-free Horizon 1 Agent proof with:

```bash
uv run --project sdks/python python tooling/scripts/validate_agent_studio_e2e.py
```

The validator creates and removes an isolated test identity and API key. If the
local Studio already contains users, provide the existing administrator
credentials through `JUNJO_STUDIO_E2E_EXISTING_EMAIL` and
`JUNJO_STUDIO_E2E_EXISTING_PASSWORD`; the values are never accepted as command
arguments or written to output.

See the scoped `AGENTS.md` and README in each component before changing it.
Cross-system changes must update the canonical contract and validate every
affected producer and consumer in one pull request.

## Versions and releases

Components are versioned independently. New release tags are namespaced:

- `sdk-python-v<version>` publishes the Python `junjo` package.
- `studio-v<version>` publishes the synchronized Studio service images.
- the telemetry contract has its own integer version in
  [`contracts/telemetry/VERSION`](contracts/telemetry/VERSION).

## Licensing

All Junjo-authored source, applications, documentation, contracts, examples,
and deployment distributions are licensed under the Apache License 2.0. See
the root [`LICENSE`](LICENSE) and the license copies shipped with independently
packaged components, including the [Python SDK](sdks/python/LICENSE),
[Studio](apps/studio/LICENSE), [website](apps/website/LICENSE),
[minimal deployment](apps/studio/deployments/minimal/LICENSE), and
[VM/Caddy deployment](apps/studio/deployments/vm-caddy/LICENSE).

Third-party dependencies and bundled notices remain subject to their own
licenses. Studio's incorporated-source notices and historical provenance are
recorded in [`apps/studio/THIRD_PARTY_NOTICES.md`](apps/studio/THIRD_PARTY_NOTICES.md)
and [ADR 0002](docs/adr/0002-platform-licensing-and-third-party-material.md).

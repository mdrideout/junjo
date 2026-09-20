# Junjo for Coding Agents

Read the root `AGENTS.md` and ADR 0017 before changing this component.

- This application owns the MCP handoff runtime, host telemetry adapters, and
  installable coding-agent plugin. It has its own Python package and lockfile.
- The coding host performs reasoning and spawns native workers. Do not add
  model API clients or silently substitute application-owned agents.
- Execute real SDK Workflows, Graphs, Nodes, Conditions, and Stores. Do not
  implement a second graph interpreter in prompts or in the bridge.
- Studio receives OTLP traces through its existing ingestion interface. Do
  not depend on Studio implementation modules or assign native Junjo identity
  to external host spans.
- Preserve source evidence and report missing capture. Never manufacture model
  timings, token counts, source identities, or successful live validation.
- Run `uv sync --frozen`, `uv run ruff check .`, `uv run ruff format --check .`,
  `uv run ty check`, `uv run pytest -q`, and `uv build` for runtime changes.
  For adapter changes also run the live proof described in the README.
- Keep local credentials, host transcripts, and generated evidence under
  ignored paths. Committed evidence must be deliberately reviewed and contain
  only this fixture's scoped output.

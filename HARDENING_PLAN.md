# Junjo Hardening Plan

This plan tracks the remaining hardening work after the major runtime and store
correctness fixes already completed on `workflow-hardening`.

The goal of this document is to stay truthful and actionable. Completed work is
summarized briefly. Open work is described in more detail.

## Current Status

### Completed

- Workflow and subflow execution isolation
- Per-run `ExecutionResult`
- Parent-scope loop protection
- `RunConcurrent` fail-fast sibling cancellation
- Cancellation telemetry for cancelled sibling branches
- Deep detached `get_state()` snapshots
- Atomic validation and commit in `BaseStore.set_state()`
- Removal of the old subscriber implementation
- Replacement of `HookManager` with the new `Hooks` + internal lifecycle split
- Graph validation, compilation, structural IDs, and rendering hardening
- Public docstring, docs, and example alignment for the hardened runtime model

### Partially Complete

- Regression coverage for major known runtime/store failures
- Documentation and example truthfulness
- Changelog and agent guidance cleanup

### Still Open

- CI and release hardening
- Production-safe observability controls
- Release/process discipline improvements

## Completed Work

### 1. Execution Runtime Hardening

Status: completed

Delivered:

- `Workflow` and `Subflow` now execute against a per-run execution context.
- Workflow definitions are reusable and no longer act like live mutable run containers.
- `Workflow.execute()` returns an `ExecutionResult`.
- Parent workflow loop protection applies to subflow loops.
- Workflow-local execution counts stay scoped to the current workflow level.
- `RunConcurrent` now cancels pending siblings on failure and raises deterministically.
- Cancelled branches are recorded as cancelled in telemetry instead of being treated like ordinary errors.

### 2. State And Store Hardening

Status: completed for the current patch-oriented API

Delivered:

- `BaseStore.get_state()` now returns a detached deep snapshot.
- `BaseStore.set_state()` now validates and commits against the current locked state.
- Interleaved updates can no longer validate against stale state and commit an invalid final model.
- The old subscriber implementation was removed instead of being redesigned.

### 3. Lifecycle Hooks

Status: completed for v1

Delivered:

- The old telemetry-shaped hook system was removed.
- Public `Hooks` now provide typed lifecycle callbacks.
- Runtime execution, internal lifecycle dispatch, public hooks, and telemetry are separated.
- Hook failures are isolated and recorded without failing workflow execution.
- State change hooks now receive detached state snapshots and JSON patch payloads.

### 4. Docs And Example Truthfulness

Status: largely completed

Delivered:

- Public runtime docstrings were updated instead of being shortened away.
- `Workflow` and `Subflow` constructor docs remain on `__init__` for generated docs and hover help.
- Examples now separate workflow definition from hook/logging wiring.
- Hook documentation and examples now show real usage rather than placeholder configuration.

### 5. Graph Hardening

Status: completed

Delivered:

- `Graph` now uses explicit plural `sinks` for terminal nodes.
- Traversal follows ordered first-match semantics directly.
- `Graph.validate()` and `Graph.compile()` now provide a canonical validated structural model.
- Typed graph exceptions now distinguish validation, compilation, serialization, and rendering failures.
- Graph, node, and edge structural IDs are now separate from runtime execution IDs.
- DOT, Graphviz, and Mermaid rendering now consume `CompiledGraph` directly.
- Graph definitions are immutable after construction, so compiled snapshots cannot silently go stale.

## Phase A - CI And Release Hardening

### Why this is still open

The code is much safer now, but the repo still does not have a strong automated
gate around those guarantees.

### Remaining changes

- Add real PR/push CI for library health:
  - `uv run ruff check .`
  - `uv run pytest -q`
  - `uv run mypy`
  - `python -m build`
  - `twine check dist/*`
- Make publish depend on green CI.
- Separate hermetic library health from optional example or provider-backed evals.
- Decide whether current package maturity signaling is still justified.

### Exit criteria

- Publish depends on green CI.
- Core library CI is hermetic and trustworthy.
- Example/integration evals no longer define package health implicitly.

## Phase B - Observability Operational Safety

### Why this is still open

Telemetry correctness improved, but operational controls are still missing.
Core runtime paths still use `print()` and there is no real telemetry
configuration model for redaction, payload size, or capture profiles.

### Remaining changes

- Replace runtime `print()` calls with package logging.
- Introduce explicit telemetry configuration:
  - state capture policy
  - graph capture policy
  - patch capture policy
  - redaction/masking support
  - size ceilings
  - AI Studio vs generic OTLP profiles
- Add explicit exporter lifecycle behavior such as shutdown/flush expectations.
- Consider versioning Junjo-specific telemetry schema fields.

### Exit criteria

- Core runtime emits through logging instead of `print()`.
- Telemetry payload controls are configurable and documented.
- Exporter lifecycle and failure behavior are explicit.

## Phase C - Quality Gates And Release Discipline

### Why this is still open

Docs and examples improved substantially, but long-term repo discipline is
still mostly process, not code.

### Remaining changes

- Keep root CI focused on hermetic library health.
- Classify optional example/integration tests separately.
- Keep changelog entries focused on library behavior, with examples/docs/tooling clearly separated when needed.
- Continue auditing docs/examples whenever public behavior changes.

### Exit criteria

- Release notes distinguish library changes from docs/examples/tooling changes.
- Root CI reflects actual library support policy.
- Docs and examples remain aligned with shipped behavior over time.

## Superseded Decisions

These older ideas are no longer the current direction and should not be treated
as active plan items:

- Add a short-term reentrancy guard:
  replaced by safe concurrent reuse of workflow definitions.
- Add reducer-style or callback-style store mutation as the primary API:
  current direction is to keep the store API patch-oriented and simple.
- Redesign subscribers:
  subscribers were removed instead.
- Decide whether hooks are supported:
  hooks are now supported and implemented via the new lifecycle architecture.
- Stage breaking changes behind flags/deprecations first:
  current direction for this hardening work is greenfield cleanup without
  backward-compatibility baggage unless explicitly required.

## Recommended Next Order

1. CI and release hardening
2. Observability operational controls
3. Long-term release/process discipline

## Final Note

The highest-risk runtime correctness work is already done. The remaining work is
primarily about:

- making observability production-safe
- making release quality enforceable by process instead of memory

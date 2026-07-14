# Junjo SDK Library AGENTS.md

Note: Junjo is a Python graph-based LLM workflow library. This directory owns
the Python SDK, which pairs through explicit telemetry contracts with Junjo AI
Studio under `/Users/matt/repos/junjo/apps/studio`.

Public behavior, examples, and conceptual explanations live in:

- public class and function docstrings
- source-owned docs and exports under `/Users/matt/repos/junjo/sdks/python/docs`
- runnable examples under `/Users/matt/repos/junjo/sdks/python/examples`

## Developer Philosophy

- Be grug brained.
- Everything here is greenfield. No fallbacks, deprecations, or backward compatibility are required. Do not carry through baggage when we are refactoring.
  - Breaking changes are okay, but document them and update the shared
    telemetry contract and Studio consumers when compatibility is affected.
- Do thorough, complete work. Do not try to save time. Do not do bandaids. Do proper complete well architected work.
- Do not use abstractions unless repetition has become brittle.
- Use single responsibility principle and separation of concerns.
- No clever code. Use principle of least astonishment. No misdirection. Write simple, explicit code.
- Ground all plans, strategy, and analysis in the code. Do not make assumptions about what is in files.
- Avoid scope creep - do not re-write or change code that is not within the scope of the task unless it is directly related.

## Repository Overview

- Junjo is Python library for Python Application Developers who are building Graph-Based AI workflows where the workflow graph is conditionally traversed according to application state.
- Public APIs and docstrings are part of the product, not incidental comments. Maintain them properly for public doc consumption.
- OpenTelemetry is a first-class runtime concern.
- Hooks are optional observers, not the control plane for telemetry.
- Workflow execution is isolated per run. A `Workflow` or `Subflow` object is a reusable definition, not a live mutable run container.
- `Workflow.execute()` returns an `ExecutionResult`.
- `BaseStore.get_state()` returns a detached deep snapshot.
- `BaseStore.set_state()` is patch-oriented and validates atomically against the current locked state.

## What AGENTS Should Optimize For

- Check ADR documents before implementation if ADRs exist for the touched area, and raise concerns if we are changing or violating architectural principles. Do not simply change ADRs to match new implementation without explicit consideration and approval. Implementation should follow ADR guidance as the source of strategic truth. If we change strategy, ADRs are updated before implementation proceeds.
- When implementation details and docs disagree, trust the latest code implementation, then fix documentation drift. Raise alarms if code implementation has significant mismatch from ADRs or docs.
- Optimize for readability and clear, transparent consumption by a Python application developer. Do not be clever. We are not creating black box abstractions for the developer. We prefer obvious, verbose implementation patterns, not low-code convenience.
- Keep separation of concerns obvious in both runtime code and examples.
- Preserve or improve the teaching surface of the library when changing code.
- Code implementation and code comments need to provide clear context and usage instructions to LLMs implementing the code.

## Public Docs Rules

- Preserve verbose public docstrings.
- If behavior changes, update the existing docstrings and examples instead of shrinking or deleting them.
- Public runtime APIs should use Sphinx/reST-friendly docstrings.
- Prefer `:param:` / `:type:` formatting in public API method docstrings.
- Keep rich API docs on `__init__` when that improves generated docs and editor hover help.
- Short class docstrings are fine, but do not move detailed constructor docs away from `__init__` unless explicitly asked.
- Preserve explicit footgun warnings when they are still true.
  Example: `Node.service()` should not be called directly.

## Examples Rules

- Keep workflow definition files focused on graph and store construction.
- Put hook registration, logging, app wiring, and telemetry setup in separate example modules or entrypoints.
- Do not add extra files or wrapper layers to examples unless they clearly improve comprehension.
- Do not show placeholder configuration that does nothing.
- If a feature is added to the public API, show one concrete developer use case for it in docs or examples.
  Example: log `on_workflow_completed` with `run_id`, `trace_id`, and final state.

## Architecture Rules

- Keep runtime execution, lifecycle dispatch, public hooks, and telemetry as separate concerns.
- We intentionally clearly separate Workflow / Graph / State / and Execution layers cleanly.
- Telemetry must not depend on public hooks.
- Prefer an internal lifecycle layer over constructing public hook events directly inside runtime modules.
- Do not couple workflow execution files to example-only or logging-only concerns.

## Store And State Rules

- Keep the public store API patch-oriented and simple.
- The library owns correct state transition mechanics.
- Consumers own domain invariants and action boundaries.
- Do not expose live mutable store internals through public result or hook APIs unless explicitly required.
- State and store are inspired by Redux and the Elm Pattern. Follow our exposed interaction patterns cleanly.

## When Editing Public Surfaces

Whenever behavior or public APIs change, update all of the following together:

1. ADRs / strategic documentation (if new decisions made)
2. runtime code
3. tests
4. public docstrings
5. Python docs source, the Sphinx migration build, and the generated Starlight export
6. examples

Be comprehensive so that we avoid documentation drift, or potential LLM context poison from outdated materials.

## Validation Checklist

For meaningful public-surface changes, run:

- `uv run ruff check .`
- `uv run pytest -q`
- `uv run ty check --error-on-warning src`
- `uv run sphinx-build -b html docs docs/_build/html`
- the Python documentation export and parity validation commands documented in
  `sdks/python/docs/README.md`

If Sphinx warnings appear, do not ignore them by default. Check whether they
were pre-existing or introduced by the change. Suggest the fixes.

## File Map

- `/Users/matt/repos/junjo/sdks/python/src/junjo/workflow.py`: workflow and subflow execution
- `/Users/matt/repos/junjo/sdks/python/src/junjo/store.py`: state management
- `/Users/matt/repos/junjo/sdks/python/src/junjo/node.py`: node execution contract
- `/Users/matt/repos/junjo/sdks/python/src/junjo/run_concurrent.py`: concurrent execution behavior
- `/Users/matt/repos/junjo/sdks/python/src/junjo/hooks.py`: public hook API
- `/Users/matt/repos/junjo/sdks/python/src/junjo/_lifecycle.py`: internal lifecycle dispatch
- `/Users/matt/repos/junjo/sdks/python/src/junjo/telemetry`: OpenTelemetry implementation
- `/Users/matt/repos/junjo/sdks/python/docs`: public documentation
- `/Users/matt/repos/junjo/sdks/python/examples`: runnable examples

## Core Concepts To Inspect

- `/Users/matt/repos/junjo/sdks/python/src/junjo/state.py`: `BaseState`
- `/Users/matt/repos/junjo/sdks/python/src/junjo/store.py`: `BaseStore`
- `/Users/matt/repos/junjo/sdks/python/src/junjo/node.py`: `Node`
- `/Users/matt/repos/junjo/sdks/python/src/junjo/edge.py`: `Edge`
- `/Users/matt/repos/junjo/sdks/python/src/junjo/condition.py`: `Condition`
- `/Users/matt/repos/junjo/sdks/python/src/junjo/graph.py`: `Graph`
- `/Users/matt/repos/junjo/sdks/python/src/junjo/workflow.py`: `Workflow`, `Subflow`, `_NestableWorkflow`, `ExecutionResult`
- `/Users/matt/repos/junjo/sdks/python/src/junjo/run_concurrent.py`: `RunConcurrent`
- `/Users/matt/repos/junjo/sdks/python/src/junjo/hooks.py`: public hooks API
- `/Users/matt/repos/junjo/sdks/python/src/junjo/_lifecycle.py`: internal lifecycle dispatch
- `/Users/matt/repos/junjo/sdks/python/src/junjo/telemetry`: OpenTelemetry implementation

## Anti-Patterns To Avoid

- Do not rewrite or shrink helpful public docstrings without maintaining full guidance and context.
- Do not mixing hook wiring or app bootstrapping into workflow definition modules when a separate entrypoint is clearer.
- Do not add abstraction layers that make examples or public APIs harder to understand.
- Do not treat AGENTS.md as a duplicate of the public docs. AGENTS.md is for runtime guidance and context needed for every Agent run.

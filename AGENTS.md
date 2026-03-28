# Junjo Agent Guide

This file is for code-writing agents working in the Junjo repo.

Do not treat this as the main source of API truth. Public behavior, examples,
and conceptual explanations should live in:

- public class and function docstrings
- Sphinx docs under `/Users/matt/repos/junjo/docs`
- runnable examples under `/Users/matt/repos/junjo/examples`

Use this file for repo-specific implementation guidance and authoring rules.

## Code Opinions

- Be grug brained in approaches
- Use clear separation of concerns
- Do not create abstractions for single-use cases where inline is easier to understand
- Do not build complex multi-line ternaries when clear if / else is more readable. Ternaries for very simple only.
- Prefer more verbose, single purpose clear separation code over combined concepts or dual / multi-purpose functions.
- Treat everything as greenfield: no fallbacks, deprecations, backward compatibility, or baggage should be carried through to new ideas.
  - Keep track of all breaking changes to incorporate into release notes, but do not worry about causing breaking changes.
  - These can go inside a "FUTURE RELESE" section of the changelog
  - Document major changes and breaking changes in the CHANELOG.md as we go (not implementation details in the weeds)
  - CHANGELOG.md should have the newest changes at the top

## Repo Truths

- Junjo is a Python library for Python application developers.
- Junjo is for building Graph-Based AI workflows where the workflow is conditionally traversed according to state.
- Public APIs and docstrings are part of the product, not incidental comments.
- OpenTelemetry is a first-class runtime concern.
- Hooks are optional observers, not the control plane for telemetry.
- Workflow execution is isolated per run. A `Workflow` or `Subflow` object is a reusable definition, not a live mutable run container.
- `Workflow.execute()` returns an `ExecutionResult`.
- `BaseStore.get_state()` returns a detached deep snapshot.
- `BaseStore.set_state()` is patch-oriented and validates atomically against the current locked state.

## What AGENTS Should Optimize For

- Prefer the least surprising design over the most abstract one.
- Optimize for readability by a Python application developer, not framework cleverness.
- Keep separation of concerns obvious in both runtime code and examples.
- Preserve or improve the teaching surface of the library when changing code.

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
- Avoid coupling workflow execution files to example-only or logging-only concerns.
- Avoid introducing compatibility scaffolding in greenfield work unless explicitly requested.

## Store And State Rules

- Keep the public store API patch-oriented and simple.
- The library owns correct state transition mechanics.
- Consumers own domain invariants and action boundaries.
- Do not reintroduce stale validate-then-apply behavior.
- Do not expose live mutable store internals through public result or hook APIs unless explicitly required.

## When Editing Public Surfaces

Whenever behavior or public APIs change, update all of the following together:

1. runtime code
2. tests
3. public docstrings
4. Sphinx docs
5. examples

Do not stop after tests pass if the docs/examples are now misleading.

## Validation Checklist

For meaningful public-surface changes, run:

- `uv run ruff check .`
- `uv run pytest -q`
- `uv run sphinx-build -b html docs docs/_build/html`

If Sphinx warnings appear, do not ignore them by default. Check whether they
were pre-existing or introduced by the change.

## File Map

- `/Users/matt/repos/junjo/src/junjo/workflow.py`: workflow and subflow execution
- `/Users/matt/repos/junjo/src/junjo/store.py`: state management
- `/Users/matt/repos/junjo/src/junjo/node.py`: node execution contract
- `/Users/matt/repos/junjo/src/junjo/run_concurrent.py`: concurrent execution behavior
- `/Users/matt/repos/junjo/src/junjo/hooks.py`: public hook API
- `/Users/matt/repos/junjo/src/junjo/_lifecycle.py`: internal lifecycle dispatch
- `/Users/matt/repos/junjo/src/junjo/telemetry`: OpenTelemetry implementation
- `/Users/matt/repos/junjo/docs`: public documentation
- `/Users/matt/repos/junjo/examples`: runnable examples

## Core Concepts To Inspect

- `/Users/matt/repos/junjo/src/junjo/state.py`: `BaseState`
- `/Users/matt/repos/junjo/src/junjo/store.py`: `BaseStore`
- `/Users/matt/repos/junjo/src/junjo/node.py`: `Node`
- `/Users/matt/repos/junjo/src/junjo/edge.py`: `Edge`
- `/Users/matt/repos/junjo/src/junjo/condition.py`: `Condition`
- `/Users/matt/repos/junjo/src/junjo/graph.py`: `Graph`
- `/Users/matt/repos/junjo/src/junjo/workflow.py`: `Workflow`, `Subflow`, `_NestableWorkflow`, `ExecutionResult`
- `/Users/matt/repos/junjo/src/junjo/run_concurrent.py`: `RunConcurrent`
- `/Users/matt/repos/junjo/src/junjo/hooks.py`: public hooks API
- `/Users/matt/repos/junjo/src/junjo/_lifecycle.py`: internal lifecycle dispatch
- `/Users/matt/repos/junjo/src/junjo/telemetry`: OpenTelemetry implementation

## Anti-Patterns To Avoid

- Rewriting or shrinking helpful public docstrings without replacing the lost guidance.
- Mixing hook wiring or app bootstrapping into workflow definition modules when a separate entrypoint is clearer.
- Adding abstraction layers that make examples or public APIs harder to understand.
- Treating AGENTS.md as a duplicate of the public docs.
- Letting tests pass while docs or examples drift out of date.

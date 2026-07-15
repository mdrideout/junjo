---
title: "Hooks"
description: "Observe Junjo Workflow and Agent lifecycle events with optional in-process Python hook callbacks."
---
<!-- migrated-from: sdks/python/docs/hooks.rst; source-hash: sha256:d4fdd8e32222a2df8291d4694a51d8a802ed11890a30f29dd043719a5f4d255a -->
<!-- migrated-keywords: junjo, python, hooks, lifecycle events, callbacks, workflow observability, state changes -->

<a id="hooks"></a>
Junjo hooks are optional, in-process Python callbacks for observing Workflow
and Agent lifecycle events. Hooks do not control execution, and they are
separate from OpenTelemetry, which stays active whether or not you register
hooks.

## Simple completion logging

```python
from junjo import BaseState, BaseStore, Graph, Hooks, Node, Workflow
from junjo.hooks import WorkflowCompletedEvent

class MyState(BaseState):
    message: str = "hello"

class MyStore(BaseStore[MyState]):
    pass

class MyNode(Node[MyStore]):
    async def service(self, store: MyStore) -> None:
        return None

def create_graph() -> Graph:
    node = MyNode()
    return Graph(source=node, sinks=[node], edges=[])

hooks = Hooks()

def log_completed(event: WorkflowCompletedEvent[MyState]) -> None:
    print(
        event.hook_name,
        {
            "workflow_name": event.name,
            "run_id": event.run_id,
            "executable_definition_id": event.executable_definition_id,
            "executable_runtime_id": event.executable_runtime_id,
            "executable_structural_id": event.executable_structural_id,
            "enclosing_graph_structural_id": event.enclosing_graph_structural_id,
            "trace_id": event.trace_id,
            "span_id": event.span_id,
            "message": event.result.state.message,
        },
    )

hooks.on_workflow_completed(log_completed)

workflow = Workflow[MyState, MyStore](
    name="My Workflow",
    graph_factory=create_graph,
    store_factory=lambda: MyStore(initial_state=MyState()),
    hooks=hooks,
)

async def main() -> None:
    await workflow.execute()

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
```

## Shared hook fields

Hook callbacks receive one immutable event object. Every hook event includes:

- `event.run_id`: the unique execution id for this run
- `event.executable_definition_id`: the stable id of the workflow, subflow, or node definition
- `event.hook_name`: the lifecycle hook name such as `workflow_completed`
- `event.executable_runtime_id`: the runtime id of the executable that fired the hook
- `event.executable_structural_id`: the stable structural id of the executable that fired the hook
- `event.parent_executable_runtime_id` / `event.parent_executable_structural_id`: parent executable identities when the hook fires inside a nested execution scope
- `event.span_type`: the Junjo span type of the executable that fired the hook
- `event.trace_id` / `event.span_id`: OpenTelemetry correlation ids

Workflow, subflow, Node, concurrent, and state-change events also include
`event.enclosing_graph_structural_id`. It identifies the explicit Graph that
encloses that executable. Agent events do not expose this Graph-only field.

## Additional hook fields

Different lifecycle events carry additional fields for the specific event type:

- Workflow and subflow start events include `event.store_id` and `event.graph_json`.
- Workflow and subflow completion events include `event.store_id` and `event.result`. Use `event.result.state` to inspect the final state snapshot.
- Failure events include `event.error`. Workflow and subflow failure events also include `event.state`.
- Cancellation events include `event.reason`. Workflow and subflow cancellation events also include `event.state`.
- Agent lifecycle uses `on_agent_started`, `on_agent_completed`,
  `on_agent_failed`, and `on_agent_cancelled`. Agent events contain truthful
  common executable identity plus Agent key and Store ID, without fabricated
  Graph fields. Completion includes a detached result; failure and cancellation
  include detached diagnostic state.
- Callback membership is snapshotted when an execution is admitted. Registering
  or unsubscribing during a run affects future runs only.
- Node and run-concurrent lifecycle events include `event.store_id` and `event.parent_executable_definition_id`. They do not include final state snapshots.
- State-change events include `event.store_id`, `event.store_name`, `event.action_name`, `event.patch`, `event.state`, and `event.parent_executable_definition_id`.

## Registering and unsubscribing

Every `hooks.on_*()` registration method returns an unsubscribe callback.
Call that returned function when you want to remove the callback from the
registry.

```python
unsubscribe = hooks.on_workflow_completed(log_completed)

# Later, if the callback should no longer run:
unsubscribe()
```

Hook event state payloads are Python-side lifecycle data, not serialized
OpenTelemetry payloads. `event.state` is a detached copied state object for
in-process inspection inside your callback. That means telemetry-oriented state
serialization choices such as field exclusion or truncation do not
automatically change what appears on `event.state`.

For `on_state_changed`, the executable identity fields describe the active
workflow, subflow, node, or concurrent executable that actually triggered the
state update. The parent executable fields describe the containing execution
scope around that update.

## Base example

The base example app registers every public hook with simple logging so you can
see the complete lifecycle payloads that fire during a normal run:

- workflow hooks
- subflow hooks
- node hooks
- run-concurrent hooks
- state-changed hooks

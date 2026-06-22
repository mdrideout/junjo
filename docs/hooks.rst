Hooks
=====

Junjo hooks let you observe workflow lifecycle events with ordinary Python callbacks.
Hooks are optional and do not control workflow execution. OpenTelemetry remains a
built-in runtime concern even when you use hooks.

Simple completion logging
-------------------------

.. code-block:: python

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

    result = await workflow.execute()

Shared hook fields
------------------

Hook callbacks receive one immutable event object. Every hook event includes:

* ``event.run_id``: the unique execution id for this run
* ``event.executable_definition_id``: the stable id of the workflow, subflow, or node definition
* ``event.hook_name``: the lifecycle hook name such as ``workflow_completed``
* ``event.executable_runtime_id``: the runtime id of the executable that fired the hook
* ``event.executable_structural_id``: the stable structural id of the executable that fired the hook
* ``event.enclosing_graph_structural_id``: the stable structural id of the graph enclosing the executable
* ``event.parent_executable_definition_id``: the stable definition id of the parent workflow, subflow, or concurrent executable when the hook fires inside a nested execution scope
* ``event.parent_executable_runtime_id`` / ``event.parent_executable_structural_id``: parent executable identities when the hook fires inside a nested execution scope
* ``event.trace_id`` / ``event.span_id``: OpenTelemetry correlation ids

Additional hook fields
----------------------

Different lifecycle events carry additional fields for the specific event type:

* Workflow and subflow start events include ``event.store_id`` and ``event.graph_json``.
* Workflow and subflow completion events include ``event.store_id`` and ``event.result``. Use ``event.result.state`` to inspect the final state snapshot.
* Failure events include ``event.error``. Workflow and subflow failure events also include ``event.state``.
* Cancellation events include ``event.reason``. Workflow and subflow cancellation events also include ``event.state``.
* Node and run-concurrent lifecycle events include ``event.store_id`` and ``event.parent_executable_definition_id``. They do not include final state snapshots.
* State-change events include ``event.store_id``, ``event.store_name``, ``event.action_name``, ``event.patch``, ``event.state``, and ``event.parent_executable_definition_id``.

Registering and unsubscribing
-----------------------------

Every ``hooks.on_*()`` registration method returns an unsubscribe callback.
Call that returned function when you want to remove the callback from the
registry.

.. code-block:: python

    unsubscribe = hooks.on_workflow_completed(log_completed)

    # Later, if the callback should no longer run:
    unsubscribe()

Hook event state payloads are Python-side lifecycle data, not serialized
OpenTelemetry payloads. ``event.state`` is a detached copied state object for
in-process inspection inside your callback. That means telemetry-oriented state
serialization choices such as field exclusion or truncation do not
automatically change what appears on ``event.state``.

For ``on_state_changed``, the executable identity fields describe the active
workflow, subflow, node, or concurrent executable that actually triggered the
state update. The parent executable fields describe the containing execution
scope around that update.

Base example
------------

The base example app registers every public hook with simple logging so you can
see the complete lifecycle payloads that fire during a normal run:

* workflow hooks
* subflow hooks
* node hooks
* run-concurrent hooks
* state-changed hooks

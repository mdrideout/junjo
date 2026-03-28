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

Common hook payloads
--------------------

Hook callbacks receive one immutable event object. Useful fields include:

* ``event.run_id``: the unique execution id for this run
* ``event.executable_definition_id``: the stable id of the workflow, subflow, or node definition
* ``event.hook_name``: the lifecycle hook name such as ``workflow_completed``
* ``event.executable_runtime_id``: the runtime id of the executable that fired the hook
* ``event.executable_structural_id``: the stable structural id of the executable that fired the hook
* ``event.enclosing_graph_structural_id``: the stable structural id of the graph enclosing the executable
* ``event.parent_executable_definition_id``: the stable definition id of the parent workflow, subflow, or concurrent executable when the hook fires inside a nested execution scope
* ``event.parent_executable_runtime_id`` / ``event.parent_executable_structural_id``: parent executable identities when the hook fires inside a nested execution scope
* ``event.trace_id`` / ``event.span_id``: OpenTelemetry correlation ids
* ``event.result.state``: final state on completion hooks
* ``event.state``: detached state snapshot on failure, cancellation, and state-changed hooks
* ``event.patch``: JSON patch string on ``on_state_changed``
* ``event.error``: original exception on failure hooks
* ``event.reason``: cancellation reason on cancellation hooks

Base example
------------

The base example app registers every public hook with simple logging so you can
see the complete lifecycle payloads that fire during a normal run:

* workflow hooks
* subflow hooks
* node hooks
* run-concurrent hooks
* state-changed hooks

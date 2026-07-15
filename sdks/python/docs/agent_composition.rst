Agent and Workflow Composition
==============================

Composition uses ordinary application boundaries. Junjo does not add a generic
Agent Node, Workflow Tool, shared Store mapper, or universal executable base.

Workflow to Agent
-----------------

An application Node reads a detached Workflow Store snapshot, maps it to Agent
input and dependencies, awaits ``Agent.execute()``, then maps the detached
result through explicit Store actions. The Agent span is a physical and
semantic child of the Node. Agent state is never the Workflow Store.

Agent to Workflow
-----------------

An application Tool service maps its validated input into a fresh Workflow
definition, awaits the normal Workflow API, and maps ``ExecutionResult`` into
the Tool output type. The hierarchy is ``Agent -> Tool operation -> Workflow``.
The Workflow retains its own Graph, Store, identities, limits, lifecycle, and
result; the Agent is its semantic parent executable.

Failure and cancellation
------------------------

An uncaught Agent error fails its Node and Workflow. The caller receives a
``WorkflowExecutionError`` with the Agent error retained as its cause. An
uncaught admitted Workflow failure inside a Tool likewise retains its typed
Workflow boundary error and original domain cause beneath ``AgentToolError``.
Cancellation propagates through every active owner and operation;
``WorkflowCancelledError`` remains an ``asyncio.CancelledError`` while adding
the admitted Workflow run identity. Parent and child limits are independent,
and completed side effects are not rolled back.

Application code may explicitly catch a known typed failure and commit a domain
recovery result. Junjo does not supply an implicit fallback, transaction,
compensation, or persistent memory policy.

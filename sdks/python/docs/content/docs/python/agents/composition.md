---
title: "Compose agents and workflows"
description: "Combine specialist agents with structured Python workflows through explicit inputs, outputs, and tools while preserving isolated state and execution evidence."
---
<!-- migrated-from: sdks/python/docs/agent_composition.rst; source-hash: sha256:b4fe3c29cc29a98d2e31611874ac7640dbf6a1703c6020807350d10f6395caf9 -->

Compose a focused specialist with a structured workflow when one application
request mixes different kinds of work. For example, an exchange agent can call
a workflow that retrieves order, policy, and payment facts concurrently before
returning a typed eligibility result. Each boundary remains observable and can
be evaluated independently.

Composition uses ordinary application boundaries. Native Junjo Agents and
Workflows use explicit input/output mappings; there is no generic Agent Node,
shared Store mapper, or universal executable base. The optional
[OpenAI Agents SDK integration](/docs/python/integrations/openai-agents/) adds
framework-specific function-tool adapters for that external runtime.

## Workflow to Agent

An application Node reads a detached Workflow Store snapshot, maps it to Agent
input and dependencies, awaits `Agent.execute()`, then maps the detached
result through explicit Store actions. The Agent span is a physical and
semantic child of the Node. Agent state is never the Workflow Store.

## Agent to Workflow

An application Tool service maps its validated input into a fresh Workflow
definition, awaits the normal Workflow API, and maps `ExecutionResult` into
the Tool output type. The hierarchy is `Agent -> Tool operation -> Workflow`.
The Workflow retains its own Graph, Store, identities, limits, lifecycle, and
result; the Agent is its semantic parent executable.

## Failure and cancellation

An uncaught Agent error fails its Node and Workflow. The caller receives a
`WorkflowExecutionError` with the Agent error retained as its cause. An
uncaught admitted Workflow failure inside a Tool likewise retains its typed
Workflow boundary error and original domain cause beneath `AgentToolError`.
Cancellation propagates through every active owner and operation;
`WorkflowCancelledError` remains an `asyncio.CancelledError` while adding
the admitted Workflow run identity. Parent and child limits are independent,
and completed side effects are not rolled back.

Application code may explicitly catch a known typed failure and commit a domain
recovery result. Junjo does not supply an implicit fallback, transaction,
compensation, or persistent memory policy.

## Evaluate the part and the whole

Expose focused `AgentTarget`, `WorkflowTarget`, or `NodeTarget` declarations in
one [evaluation harness](/docs/python/evaluation/#declare-one-harness). A coding
agent can first test the policy lookup or specialist answer, then rerun the
outer feature to check the mappings, tool selection, and final synthesis.

The execution trace preserves the parent/child relationships, so an unexpected
outer answer can be traced back to the nested operation that produced it.
Compare the same locked cases before and after splitting a monolithic prompt;
include all added model calls and coordination in latency and usage analysis.
This is how composition becomes a testable step in
[recursive self improvement](/docs/recursive-self-improvement/).

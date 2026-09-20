---
title: "Compose agents and workflows"
description: "Choose factory-owned or borrowed application Stores for Junjo Agents and Workflows, with explicit input/output mapping and execution-scoped state evidence."
---

Agents and Workflows can use separate application Stores or share the same live
Store. Choose the boundary that suits the application. Both keep their own
execution identity, lifecycle, result, and execution structure. An Agent also
always has private runtime state for its transcript, counters, usage, and loop;
that runtime Store is independent of application state.

The runnable [junjo_openai_sdk example](https://github.com/mdrideout/junjo/tree/master/sdks/python/examples/junjo_openai_sdk)
shows both Agent Store choices, a conditional Workflow Tool, a direct Node Tool,
and OpenInference provider telemetry.

## Choose application Store ownership

| Invocation | Application state |
| --- | --- |
| `agent.execute(input, dependencies=services)` | Uses the Agent's optional `store_factory`; without one, `context.store` and `result.application_state` are `None`. |
| `agent.execute(input, dependencies=services, store=app_store)` | Borrows that exact live Store and skips the factory. |
| `workflow.execute()` | Uses the Workflow's Store factory. |
| `workflow.execute(store=app_store)` | Borrows that exact live Store and skips the factory. A fresh Graph is still created. |
| Subflow inside a Graph | Keeps its own isolated Store, with `pre_run_actions` and `post_run_actions` for explicit mapping. |

A factory is useful when each invocation should start with independent state.
Passing a Store is useful when several capabilities should read and update the
same application state. Definitions can be reused in either pattern. Junjo does
not infer a Store from parent context: pass `store=` at each shared boundary.
The application owns the lifetime of a borrowed Store.

Creation and sharing are independent choices: a Store created by an Agent's
factory can still be passed to its Workflow Tools. The OpenAI SDK example
shares the selected application Store with both Tools in either creation mode.

Declare concrete types as `Agent[Input, Output, Dependencies, AppState, AppStore]`
and `Tool[ToolInput, ToolOutput, Dependencies, AppStore]`. Tool services receive
`AgentRunContext[Dependencies, AppStore]`, giving typed access to Store actions.
Services and clients remain in `context.dependencies`.

## Workflow calls an Agent

An application Node reads its Store, constructs the Agent's input, and awaits
`execute`. In the shared pattern, Tool actions update the same live Store that
the Workflow's other Nodes use:

```python
class AskSpecialist(Node[AppStore]):
    async def service(self, store: AppStore) -> None:
        state = await store.get_state()
        result = await specialist.execute(
            Question(text=state.question),
            dependencies=services,
            store=store,
        )
        await store.save_answer(result.output.text)
```

Sharing does not inject the Store into the model prompt or automatically save
the final output. Input construction and `save_answer` are explicit application
mappings. `result.output` is the typed model output;
`result.application_state` is the detached typed application snapshot at the
Agent's execution boundary. Neither is a live Store.

For isolated state, omit `store=store`, give the Agent a factory that initializes
its own application state, and map the returned output or application snapshot
through the Workflow's actions. The mappings can copy just the fields the caller
needs. Reusable definitions should not mutate shared factory closures to inject
per-call values; construct an invocation-specific definition when needed.

## Agent uses a Workflow or Node Tool

A normal Junjo Tool is a typed async service. It can use `context.store` directly,
call another service, execute a Node, or invoke a Workflow. No one-Node Workflow
wrapper is required:

```python
async def record_finding(input: Finding, context: AgentRunContext[Services, AppStore]) -> FindingResult:
    await RecordFindingNode(input.text).execute(context.store, context.definition_id)
    state = await context.store.get_state()
    return FindingResult(findings=state.findings)
```

Use the public `Node.execute()` lifecycle, rather than calling `service()`.
The second argument supplies its parent definition identity. Within an Agent
Tool, telemetry retains the actual `Agent -> Tool -> Node` hierarchy.

A Workflow Tool can borrow the Agent's application Store:

```python
async def review(input: ReviewInput, context: AgentRunContext[Services, AppStore]) -> ReviewResult:
    result = await review_workflow.execute(store=context.store)
    return ReviewResult(status=result.state.review_status)
```

The hierarchy is `Agent -> Tool -> Workflow`. The Workflow keeps its Graph and
conditional edges. Its Store actions become visible to subsequent Agent Tools.
For an isolated Workflow, use its factory and `execute()` without `store`, then
explicitly map `result.state` into the Tool response or Agent application Store.
The [OpenAI Agents SDK adapters](/docs/python/integrations/openai-agents/) and
[evaluation invocations](/docs/python/evaluation/) also accept an explicit
application `store`; they do not prescribe an ownership pattern.

## Concurrency and state evidence

Multiple Agent or Workflow executions can borrow a Store concurrently through
`asyncio.gather`. Inside a Graph, `RunConcurrent` still takes Nodes or Subflows;
its Nodes can invoke Agents or Workflows using the received Store. Agents and
Workflows are not new direct Graph members.

Store commits are serialized by that Store's existing lock. Model requests and
Tool work remain concurrent. Reading a snapshot, awaiting work, and replacing a
list can overwrite another writer's replacement. Junjo adds no conflict
resolution, transaction, merge, or cross-execution lock around application work.
Private Agent loop state and per-run drivers remain independent.

A Store has one transition sequence for its lifetime. Each execution observes
an interval `(start, end]` and records its own start/end snapshots. Reusing a
Store can therefore start at a nonzero revision; a no-op advances the sequence
without advancing the revision. Overlapping execution views can include the
same mutation, attributed to the actual writer span. Sharing a Store does not
change execution parentage.

Keep composed concurrent work under a common OTel trace when you want Studio
to reconstruct all those views together. Studio reconstructs from events in the
retrieved trace. It reports incomplete evidence when a necessary writer event
is missing or belongs to another trace; it does not query other traces by Store
ID or fabricate missing updates.

## Failure, cancellation, and Subflows

Committed state remains in a borrowed Store after a child fails or is cancelled.
There is no rollback. Admitted Agent errors expose private `error.state` and a
separate detached `error.application_state` when available. Failed and cancelled
Agent lifecycle events also distinguish runtime and application state. The
caller can read its live Store after cancellation.

An uncaught Agent error fails its calling Node and Workflow; a nested Workflow
failure becomes an Agent Tool error. Original causes remain available.
Cancellation propagates through active executions. Each execution keeps its
own limits and terminal lifecycle.

Subflows continue to use isolated Stores. `pre_run_actions` maps parent state
into the Subflow Store; `post_run_actions` maps results back. An Agent invoked
inside a Subflow Node may borrow that Subflow's Store. This does not connect it
to the outer Workflow's Store. See [Subflows](/docs/python/workflows/subflows/).

## Evaluate the part and the whole

Use focused `AgentTarget`, `WorkflowTarget`, or `NodeTarget` declarations in one
[evaluation harness](/docs/python/evaluation/#declare-one-harness). A coding
agent can test an individual lookup, conditional branch, or specialist answer,
then rerun the outer feature to verify state mappings and final synthesis.
Include model calls and coordination in latency and usage comparisons.

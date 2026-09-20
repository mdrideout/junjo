# Junjo + OpenAI SDK + OpenInference

Start here for a native Junjo Agent using the OpenAI Python SDK. An order-support
Agent looks up an order with a Node tool, checks a fictional return policy with
a conditional Workflow tool, and produces a typed answer. All three executions
use one typed application Store, so the facts behind the answer are inspectable
in Junjo AI Studio.

| Responsibility | Library |
| --- | --- |
| Agent loop, validated Tools, conditional Workflow, typed application state | Junjo |
| Responses API requests and responses | OpenAI Python SDK |
| Provider-call spans and captured request, response, and usage fields | OpenInference OpenAI instrumentor |
| Trace storage and state exploration | Junjo AI Studio |

This example uses the OpenAI **client SDK**. The separate
[`base_openai_agents`](../base_openai_agents) example uses the OpenAI **Agents SDK**
as an external Agent runtime. Find other library combinations in the
[examples and integrations index](https://junjo.ai/docs/examples-and-integrations/).

## Setup and run

Start or reuse [Junjo AI Studio](https://junjo.ai/docs/studio/deployment/) and
create an application telemetry API key in its **API Keys** screen. The SDK and
Studio must both support telemetry contract **3** for application Store views.
From this example directory:

```bash
uv sync --frozen --package junjo-openai-sdk-example --group dev
cp .env.example .env
```

Fill in `OPENAI_API_KEY`, `OPENAI_MODEL`, and `JUNJO_AI_STUDIO_API_KEY`. Choose a
model available to your account that supports Responses function tools and
structured output. Set the Studio URL and OTLP/gRPC endpoint for your deployment.
The sample addresses are for a Python process running on the same host as local
Studio. Use `ingestion:26155` from Studio's Docker network. Use TLS and the
appropriate endpoint for a remote deployment.

The sample policy allows returns within 30 days of delivery, evaluated as of
**2026-09-20**. That fixed date makes the outcomes reproducible; there is no
order database or refund operation.

| Order | Item | Delivered | Days since delivery | Expected decision |
| --- | --- | --- | --- | --- |
| `ORD-1001` | Desk lamp | 2026-09-10 | 10 | Eligible |
| `ORD-1002` | Travel mug | 2026-08-01 | 50 | Ineligible |

```bash
# Factory-created application Store; eligible order.
uv run --frozen --package junjo-openai-sdk-example --env-file .env python main.py ORD-1001

# Caller-supplied application Store; ineligible order.
uv run --frozen --package junjo-openai-sdk-example --env-file .env python main.py ORD-1002 --store borrowed
```

Either order works with either `--store owned` (the default) or `--store borrowed`.
For example, pass `ORD-1001 --store borrowed --question "Why can I return my lamp?"`.
These commands make real provider calls. Each prints the typed final answer,
detached application state, trace ID, and Studio URL. Model wording may vary;
the Nodes determine eligibility from the recorded facts.

[main.py](main.py) calls the shared [telemetry bootstrap](telemetry.py) before
creating model work. Workers and diagnostic probes should use that same
initialization path. The OpenAI client closes before the provider shuts down
and drains its export queue. A successful model response or local queue drain
alone does not prove Studio received the trace; use the walkthrough below to
verify it. Explicit paid provider smoke tests belong in setup or diagnostics,
rather than running on every application startup.

## Follow the application state

[application.py](application.py) declares `OrderSupportState` and named
`OrderSupportStore` actions. State holds the retrieved order, evaluation date,
return window, computed age, policy check, eligibility, and decision reason.
The Agent chooses Tools; Python code performs the lookup and policy decision.

| Writer | Store action | Meaningful state change |
| --- | --- | --- |
| `LookupOrderNode` | `record_order` | Save deterministic order facts and clear any previous order's decision. |
| `EvaluateReturnPolicyNode` | `record_policy_evaluation` | Record `days_since_delivery` and `within_return_window`. |
| `EligibleReturnNode` or `IneligibleReturnNode` | `record_decision` | Record `eligible` and `decision_reason` on the selected path. |

The lookup Tool executes its Node directly through the public lifecycle:

```python
await LookupOrderNode(input.order_id).execute(context.store, context.definition_id)
```

`context.store` is the Agent's typed application Store; the second argument
identifies the parent definition. `Node.execute()` supplies Node tracing and
lifecycle handling. Do not call `Node.service()` directly or introduce a
single-Node Workflow wrapper.

The eligibility Tool lends that same Store to its Workflow:

```python
result = await return_eligibility_workflow.execute(store=context.store)
return eligibility_result(result.state)
```

The Workflow keeps its own Graph and execution identity. Its conditional edge
reads `within_return_window` after the evaluation Node commits it:

```text
EvaluateReturnPolicyNode
├── WithinReturnWindow is true → EligibleReturnNode
└── fallback                   → IneligibleReturnNode
```

Sharing does not automatically put state into prompts. `LookupOrderResult` and
`eligibility_result()` explicitly select the facts returned to the model.
The final `SupportAnswer` lives in `result.output`; it is not automatically
written into application state. `result.application_state` is a separate,
detached snapshot taken when the Agent finishes.

## Investigate the execution in Studio

Run each sample order, open the printed Studio URL, and locate the trace using
its printed trace ID and service name `junjo_openai_sdk`.

1. Open **Order support** and inspect its application state. Follow the lookup,
   policy evaluation, and decision updates, including the recorded Store action
   and writer Node. This shows the application facts independently of the
   model's prose.
2. Open **ReturnEligibilityWorkflow**. Its starting state already contains the
   order from the direct Node tool. Compare `days_since_delivery` and
   `within_return_window` with the executed conditional path and final decision.
3. Inspect the Agent's tool operations and private runtime state to see the
   normalized arguments, returned facts, and final model answer. Compare the
   eligibility Tool's result with what the model ultimately said.
4. Open the OpenInference LLM spans beneath the Agent's model-request operations.
   These show provider evidence according to the configured capture settings.
   Verify that they belong to the same trace as the Junjo state evidence.

| Investigation question | Evidence to inspect |
| --- | --- |
| What facts were available before the decision? | Order state after `record_order`, and the Workflow's starting snapshot. |
| Which action changed a field? | The state patch, named Store action, and actual writer Node. |
| What state selected the conditional path? | `within_return_window` after `record_policy_evaluation`, followed by the executed branch. |
| What did the nested Workflow return to the Agent? | The Workflow's ending state and normalized eligibility Tool result. |
| Did the issue begin in retrieved data, policy logic, tool arguments, or model synthesis? | Compare those successive boundaries with the final typed answer and provider spans. |

This granular state awareness lets you locate the first incorrect fact or
decision without reconstructing application behavior from natural-language
logs. The same typed state drives the application's control flow and supports
focused checks of a Node, Workflow, or Agent.

The application Store has one live identity and transition sequence. Each
execution records its own start/end snapshot and interval. In this example,
the Agent sees all three mutations; the Workflow starts after lookup and sees
the two policy mutations. Changes are emitted once on their actual writer
spans. The Agent also has an independent **private runtime Store** for its
transcript, counters, usage, and loop; `context.store` never refers to it.

If provider spans are missing, check that OpenInference initialized before the
calls. If the whole execution is missing, check the exporter errors, endpoint,
transport security, and Studio telemetry key. See the
[OpenInference guide](https://junjo.ai/docs/observability/opentelemetry/#native-model-sdks-with-openinference)
for capture controls and delivery verification.

## Choose where Stores are created and shared

Store creation and sharing are separate choices. `--store owned` lets the Agent's
factory create an application Store. `--store borrowed` constructs the Store
in the caller and passes `store=store` to the Agent. **Both modes share the
selected Store with the Node and Workflow tools.** Neither mode changes the
Agent's private runtime isolation.

A Workflow can use the same Agent from one of its Nodes. With `agent` built from
the model binding as in `main.py`, the Node constructs explicit model input:

```python
from junjo import Node
from application import OrderSupportStore, SupportRequest

class AskSupport(Node[OrderSupportStore]):
    def __init__(self, request: SupportRequest) -> None:
        super().__init__()
        self.request = request

    async def service(self, store: OrderSupportStore) -> None:
        result = await agent.execute(self.request, dependencies=None, store=store)
        # Tool actions have already updated the Workflow's live Store.
        # result.output is the final model answer, available for explicit mapping.
```

If the surrounding application needs to retain that answer in its state, add an
answer field and a Store action, then call that action with `result.output`.
The [composition guide](https://junjo.ai/docs/python/agents/composition/#workflow-calls-an-agent)
shows this mapping. That subsequent write belongs to the calling Workflow's
execution interval; it does not change the Agent's already captured snapshot.

For an isolated Workflow tool, initialize a new Store from selected input facts
and explicitly map selected results back. Using the imports and types in
`application.py`, this is an alternative Tool service; the main example
continues using the shared version:

```python
async def check_return_eligibility_isolated(
    input: EligibilityInput, context: AgentRunContext[None, OrderSupportStore]
) -> EligibilityResult:
    parent = await context.store.get_state()
    workflow = Workflow[OrderSupportState, OrderSupportStore](
        name="Isolated return eligibility",
        graph_factory=return_eligibility_graph,
        store_factory=lambda: OrderSupportStore(OrderSupportState(
            order=parent.order,
            as_of=parent.as_of,
            return_window_days=parent.return_window_days,
        )),
    )
    result = await workflow.execute()
    decision = eligibility_result(result.state)
    await context.store.record_decision(decision.eligible, decision.decision_reason)
    return decision
```

Here the policy calculation stays in the Workflow's Store; the caller receives
only the mapped decision. Omit the `record_decision` call if only the Tool
response should expose that result. An Agent can likewise use its factory and
map its returned application snapshot/output into a separate caller's Store.
Choose these boundaries according to which state the executions should share.

Concurrent Agents and Workflows may share a Store. Its lock orders individual
commits; it does not turn read/await/write operations into transactions or
prevent stale replacements. Keep composed work under one trace when you want
Studio to reconstruct all its writes together; missing writer events, including
writes in another trace, make the affected reconstruction incomplete. The
[composition guide](https://junjo.ai/docs/python/agents/composition/)
covers these choices and Subflows' unchanged isolation with pre/post mapping.

## Read and test the small pieces

- [application.py](application.py): typed state/actions, direct Node tool,
  conditional Workflow tool, and Agent definition.
- [driver.py](driver.py): application-owned `ModelDriver` translating Responses
  function calls into Junjo Tool calls. Each run gets its own provider
  continuation list; complete Responses output, including reasoning items,
  is retained for subsequent requests.
- [telemetry.py](telemetry.py): one OTel provider, Junjo export, and OpenInference.
- [main.py](main.py): configuration, client lifetime, Store creation choice,
  execution, and telemetry shutdown.

Validate both orders with both Store choices without credentials or paid calls:

```bash
uv run --frozen --package junjo-openai-sdk-example --group dev pytest -q test_example.py
```

The test uses the real OpenAI client and OpenInference instrumentor with a
mock HTTP transport. It verifies typed answers, normalized Tool results,
provider continuation, provider-span nesting, Store identity, both conditional
paths, and replay of actual state patches within the Agent/Workflow boundaries.
It validates locally captured telemetry; use a live run and Studio inspection
to establish end-to-end delivery for your deployment.

Provider references: [Responses function calling](https://developers.openai.com/api/docs/guides/function-calling/)
and [OpenInference OpenAI instrumentation](https://arize-ai.github.io/openinference/python/instrumentation/openinference-instrumentation-openai/).

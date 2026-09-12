---
title: "Test and evaluate Junjo agents"
description: "Test agent execution deterministically with scripted model drivers, then evaluate real specialist behavior against Studio datasets and inspect failures."
---
<!-- migrated-from: sdks/python/docs/agent_testing.rst; source-hash: sha256:ec80b2fba8806eb857737acac1119961cdc6aebd56560f4db1ef966ab357f565 -->

Use deterministic tests for execution contracts and live evaluations for
application quality. `junjo.agent.testing` is the public deterministic test
boundary and has no provider dependency. Its scripted answers prove your
wiring and error handling, not a live model's accuracy.

`ScriptedModelDriver` consumes fixed response or error steps and captures the
immutable `ModelRequest` values it received. Prefer a per-run factory when
the same Agent definition is executed concurrently. Set `fixture=True` on its
`ModelDriverDescriptor` when telemetry should identify the resulting model
operations as deterministic fixture executions.

```python
from pydantic import BaseModel

from junjo import Agent, AgentLimits, ModelDriverBinding, ModelDriverDescriptor, Tool
from junjo.agent import FinalOutputResponse, ToolCall, ToolCallsResponse
from junjo.agent.testing import ScriptedError, ScriptedModelDriver

class Query(BaseModel):
    query: str

class Answer(BaseModel):
    answer: str

async def lookup(input_value, context):
    return Answer(answer="found")

driver = ScriptedModelDriver([
    ToolCallsResponse(tool_calls=[
        ToolCall(id="lookup-1", name="lookup", arguments={"query": "x"})
    ]),
    FinalOutputResponse(output={"answer": "done"}),
])

agent = Agent(
    key="lookup_test",
    name="Lookup test",
    instructions="Look up the requested fact before answering.",
    input_type=Query,
    output_type=Answer,
    model=ModelDriverBinding.shared(
        descriptor=ModelDriverDescriptor(
            driver_key="scripted", provider="junjo", model="test", fixture=True,
        ),
        driver=driver,
    ),
    tools=[Tool(
        name="lookup",
        description="Look up a fact.",
        input_type=Query,
        output_type=Answer,
        shared_service=lookup,
    )],
    limits=AgentLimits(model_requests=2, tool_calls=1),
)

result = await agent.execute(Query(query="x"), dependencies=None)
assert driver.requests[0].ordinal == 1
assert result.tool_call_completed_count == 1
```

Use `ScriptedError(error)` to prove ModelDriver failure behavior. For
cancellation tests, a small custom driver or Tool service can await an
`asyncio.Event` so the test controls the exact active boundary.

High-value deterministic assertions include:

- exact normalized requests and transcript ordering;
- whole-batch preflight before service side effects;
- limits checked before the affected operation;
- per-run factory construction and concurrent isolation;
- typed failure causes and detached diagnostic state;
- operation sequence, Store revision replay, and terminal span evidence.

Junjo performs no hidden retry or automatic output repair, so one script step
always corresponds to one started model operation.

## Evaluate real specialist behavior

Expose the application Agent through an
[`AgentTarget`](/docs/python/agents/#improve-a-specialist-independently), then
use [Studio datasets and runs](/docs/python/evaluation/) to test real prompts,
tools, and provider calls. A coding agent can turn an observed failure into
cases, compare a candidate against the baseline, and open the execution
evidence behind each change in outcome.

For an exchange specialist, test whether it applies damaged-item exceptions and
ordinary return windows correctly. Also evaluate the outer intake agent: a
correct specialist cannot fix a request routed to the wrong domain. Keep the
criteria fixed during the comparison, report operational errors separately,
and calibrate any LLM judge before relying on its decisions.

## Shared producer conformance

This section is for SDK contributors validating the telemetry contract. An
application developer does not need to copy these repository tests to evaluate
their own Agent.

The repository carries language-independent canonical producer fixtures in
`contracts/telemetry/fixtures/agent/producer`. The Python SDK test discovers
that directory exactly and executes every scenario through the real public
Agent and Workflow APIs. It never imports the fixture generator. Controlled
private fault injection is limited to the explicit admission, terminal-commit,
and unexpected-internal-error scenarios.

Run the producer gate from `sdks/python`:

```console
uv run pytest -q tests/test_agent_producer_conformance.py
```

The gate compares all contract-owned attributes and payload slots after
normalizing only volatile identities and timestamps. It covers exact Agent and
Tool structural identities, usage, error and cancellation facts, evidence-loss
counters, physical and semantic parentage, Agent/Workflow hybrid topology, and
payload modes and policies. RFC 6902 patch bodies may differ mechanically
between language implementations, so the gate instead requires exact action,
sequence, and revision evidence and independently replays both the emitted and
canonical patches from owner start state to owner end state.

When this test fails, treat it as contract drift. Change runtime semantics and
canonical fixtures together only after deciding which behavior is correct;
never make the comparison looser to hide a mismatch. Then run the dependency-
free shared validator:

```console
python3 ../../contracts/telemetry/compatibility/validate_contract.py
```

Static generic conformance is separately proved by
`tests/test_agent_typing.py` using one valid and one intentionally invalid
consumer program.

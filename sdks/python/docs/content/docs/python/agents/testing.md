---
title: "Testing Agents"
---
<!-- migrated-from: sdks/python/docs/agent_testing.rst; source-hash: sha256:ec80b2fba8806eb857737acac1119961cdc6aebd56560f4db1ef966ab357f565 -->

`junjo.agent.testing` is the public deterministic test boundary. It has no
provider dependency.

`ScriptedModelDriver` consumes fixed response or error steps and captures the
immutable `ModelRequest` values it received. Prefer a per-run factory when
the same Agent definition is executed concurrently.

```python
from junjo.agent import FinalOutputResponse, ToolCall, ToolCallsResponse
from junjo.agent.testing import ScriptedError, ScriptedModelDriver

driver = ScriptedModelDriver([
    ToolCallsResponse(tool_calls=[
        ToolCall(id="lookup-1", name="lookup", arguments={"query": "x"})
    ]),
    FinalOutputResponse(output={"answer": "done"}),
])

result = await agent.execute(input_value, dependencies=test_dependencies)
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

## Shared producer conformance

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

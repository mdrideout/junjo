---
title: "Agents"
---
<!-- migrated-from: sdks/python/docs/agents.rst; source-hash: sha256:f85c88429ba31eb96d804feb3ee8e201dd954ed956dd287f64cfdb272d3c888f -->

`Agent` is a reusable, typed Junjo executable for the case where a model
chooses the next capability at runtime. It is a sibling of `Workflow`. An
Agent has no fabricated Graph, and a Tool is an operation rather than a Node.

The definition declares all behavior-affecting structure up front:

- a stable application-owned key and display name;
- exact instructions and typed input/output boundaries;
- one provider-neutral `ModelDriverBinding`;
- an ordered collection of explicitly typed `Tool` definitions;
- positive model-request and Tool-call limits.

Every `execute` call creates a fresh run identity, private Store, transcript,
counters, usage aggregate, lifecycle snapshot, and per-run collaborator cache.
The caller owns request dependencies, history selection, persistence, provider
credentials, transactions, and product transport.

## Minimal definition

The core package deliberately owns no provider SDK. A ModelDriver translates
one immutable normalized `ModelRequest` into either `FinalOutputResponse`
or `ToolCallsResponse`.

```python
from pydantic import BaseModel

from junjo import (
    Agent,
    AgentLimits,
    ModelDriverBinding,
    ModelDriverDescriptor,
)
from junjo.agent import FinalOutputResponse
from junjo.agent.testing import ScriptedModelDriver

class Question(BaseModel):
    text: str

class Answer(BaseModel):
    text: str

driver = ScriptedModelDriver([
    FinalOutputResponse(output={"text": "deterministic answer"})
])

agent = Agent(
    key="answer_question",
    name="Answer Question",
    instructions="Answer using available evidence.",
    input_type=Question,
    model=ModelDriverBinding.shared(
        descriptor=ModelDriverDescriptor(
            driver_key="scripted",
            provider="junjo",
            model="scripted-v1",
        ),
        driver=driver,
    ),
    tools=[],
    output_type=Answer,
    limits=AgentLimits(model_requests=4, tool_calls=8),
)

result = await agent.execute(
    Question(text="What happened?"),
    dependencies=None,
)
```

The successful result always contains validated output, a detached normalized
transcript, usage evidence, identities, counters, and terminal reason. Failure
raises a typed `AgentError`; there is no output-less success result.

## Tools and dependencies

A Tool declares an object-root input schema, an output schema, and exactly one
shared service or synchronous per-run service factory. The asynchronous service
receives validated input plus a read-only `AgentRunContext`. Dependencies are
opaque application services and never enter the ModelRequest automatically.

Tool batches are fully preflighted in model order before any factory or service
side effect. Calls then run sequentially and each validated result is committed
before the next call begins.

## Limits and errors

Model-request and Tool-call limits are always positive. Budget admission occurs
before work starts, and an over-budget Tool batch is rejected as a whole.
Provider errors, malformed responses, unknown Tools, invalid arguments, service
errors, invalid Tool outputs, and invalid final output have distinct typed
errors in `junjo.agent`. `asyncio.CancelledError` propagates unchanged.
An unexpected failure in Junjo-owned admitted machinery is surfaced explicitly
as `AgentInternalError` with the original exception preserved as its cause;
it is never mislabeled as a provider or Tool failure.

History is optional, provider-neutral, immutable, and must contain complete
prior exchanges. Junjo does not create persistent conversation memory.

## Portable boundaries and deterministic identity

Every value that can enter state, telemetry, a ModelRequest, Tool arguments,
Tool results, usage, settings, or a structural fingerprint must be portable
I-JSON. Junjo rejects non-finite floats, integers outside the interoperable
`[-9007199254740991, 9007199254740991]` range, non-string object keys, and
Unicode lone surrogates. Rejection occurs at the owning boundary before the
value can mutate live state or produce an unencodable OTLP payload.
Decoded JSON has a maximum nesting depth of 128: the root is depth 0, and
object names, object values, and array elements are children. A deeper value
fails at its owning boundary.

`JsonValue` and `FrozenJsonValue` in `junjo.agent` describe the public
portable shapes. Frozen values are detached recursively; callers cannot mutate
a request, result transcript, diagnostic snapshot, or stored evidence through
a retained input reference.

Concrete JSON values take a strict JSON path and must preserve every supplied
value; declared defaults may add missing members. Non-JSON typed values take a
strict Python path and must retain their exact type and equality after declared
serialization and strict JSON detachment. Structured objects reject undeclared
members, and only declared external aliases are accepted. A lossy typed value
is not reported as a full diagnostic candidate before this proof succeeds.
Use `dict[str, T]` for intentionally open data; set-like types, one-shot
iterables, and non-string mapping keys are not portable Agent boundaries.

Agent and Tool structural identities use RFC 8785 canonical JSON and the
versioned Junjo schema-normalization profile. The profile removes generated
annotation titles, canonicalizes reachable local definitions and set-valued
schema keywords, preserves application properties named `title` and ordered
applicators, and rejects duplicate set members. Therefore class renames and
object insertion order do not change semantic identity, while instructions,
schemas, model settings, Tool order, or limits do.

Three identities remain deliberately separate:

- `definition_id` identifies one in-process definition object;
- `run_id` identifies one isolated execution;
- `structural_id` identifies language-neutral behavior-affecting material.

## Typed results and diagnostic state

`Agent[InputT, OutputT, DependenciesT]` preserves all three public generic
boundaries. Static checking proves that `execute(InputT,
dependencies=DependenciesT)` returns `AgentExecutionResult[OutputT]` and
rejects crossed input, dependency, or Tool-service output types.

After admission, typed failures expose an immutable `AgentStateSnapshot` in
`error.state` (also available as `error.evidence`). The snapshot is a
detached diagnostic projection, not the private live Store state. It contains
portable input/history/transcript evidence, usage, coherent counters, Tool-call
partitions, final-output availability, and terminal reason. Admission failures
have no Store snapshot because no run state was published.

Successful `AgentExecutionResult` construction enforces the same public
identity, transcript, usage, and counter invariants. Its terminal reason is
always `final_output`; Junjo never returns a partially successful result.

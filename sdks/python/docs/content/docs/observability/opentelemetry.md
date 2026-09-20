---
title: "OpenTelemetry for AI application evidence"
description: "Capture AI execution chronology with Junjo OpenTelemetry instrumentation. Configure export, verify Studio delivery, and understand the evidence available to coding agents."
---
<!-- migrated-from: sdks/python/docs/opentelemetry.rst; source-hash: sha256:4259e6339a291bc04bd394ad87b7d9e81a8eb369c729ecd98f60d1a8e1ff4513 -->
<!-- migrated-keywords: junjo, opentelemetry, tracing, observability, OTLP, jaeger, grafana, honeycomb -->

<a id="opentelemetry"></a>
OpenTelemetry connects application execution to the evidence your coding agent
uses for [recursive self improvement](/docs/recursive-self-improvement/). The
Junjo SDK emits native Workflow, Agent, Node, and state-update spans; your
application configures the provider, exporter, and content policy. Junjo AI
Studio stores the received traces for coding-agent queries and human inspection.

Native instrumentation does not automatically capture every call made inside a
Node. Instrument your model clients, HTTP handlers, retrieval, and other
libraries when you need their internal operations. Existing external spans can
appear in Studio's trace view without becoming native Junjo graphs or Stores.
For the first-party Python adapter, see
[OpenAI Agents SDK integration](/docs/python/integrations/openai-agents/).

Create an application telemetry credential in Studio's **API Keys** screen.
That `JUNJO_AI_STUDIO_API_KEY` admits OTLP spans only. The separate developer
access token used by the [evaluation CLI](/docs/python/evaluation/#credentials-stay-separate)
grants dataset and evidence-query access; do not swap the two credentials.

## Complete Configuration Example

Configure telemetry once for the lifetime of the application process. If the
application already owns a provider, attach the Junjo span processor to that
provider instead of installing another global provider. The following is a
standalone setup for an application that does not yet have one:

```python title="otel_config.py"
import os
from junjo.telemetry.junjo_otel_exporter import JunjoOtelExporter
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.resources import Resource

def init_telemetry(
    *, service_name: str, service_namespace: str, endpoint: str, insecure: bool = False
):
    """Configure OpenTelemetry with Junjo AI Studio."""

    # Get API key
    api_key = os.getenv("JUNJO_AI_STUDIO_API_KEY")
    if not api_key:
        raise ValueError("JUNJO_AI_STUDIO_API_KEY environment variable not set")

    # Create resource
    resource = Resource.create({
        "service.name": service_name,
        "service.namespace": service_namespace,
        "service.version": "1.0.0",
        "deployment.environment": os.getenv("ENV", "development")
    })

    # Set up tracer provider
    tracer_provider = TracerProvider(resource=resource)

    # Configure Junjo AI Studio exporter.
    junjo_exporter = JunjoOtelExporter(
        endpoint=endpoint,
        api_key=api_key,
        insecure=insecure
    )

    # Add span processor
    tracer_provider.add_span_processor(junjo_exporter.span_processor)

    # Set as global tracer provider
    trace.set_tracer_provider(tracer_provider)

    return tracer_provider
```

Use in your application:

```python
from otel_config import init_telemetry

# Local application connecting to Studio on the same host.
# Use the actual application identity here and in EvaluationHarness.
tracer_provider = init_telemetry(
    service_name="my-ai-workflow",
    service_namespace="my-company",
    endpoint="localhost:26155",
    insecure=True,
)

try:
    # Execute workflows - automatic instrumentation
    await my_workflow.execute()
finally:
    tracer_provider.shutdown()
```

## Native model SDKs with OpenInference

Junjo runs the Agent loop and records application state and normalized model/Tool
operations. The OpenAI Python SDK sends requests. The OpenInference OpenAI
instrumentor captures provider-specific request, response, and usage spans.
Junjo AI Studio receives all of them through the application's OTel provider.

### Install and initialize the provider instrumentor

Install the client and instrumentor in the application; they are not core Junjo
dependencies:

```bash
uv add openai openinference-instrumentation-openai
```

The [junjo_openai_sdk example](https://github.com/mdrideout/junjo/tree/master/sdks/python/examples/junjo_openai_sdk)
provides a locked environment and the complete order-support application: a
Responses driver, direct Node tool, conditional Workflow tool, and shared
application Store. Its README covers Studio setup, credentials, both Store
creation options, and runs that demonstrate each conditional path.

In the application's shared `init_telemetry()`, add this after configuring the
provider above and before returning it. Instrument once per process, before
creating model work:

```python
from openinference.instrumentation.openai import OpenAIInstrumentor

OpenAIInstrumentor().instrument(tracer_provider=tracer_provider)
```

Use the **same provider** that is installed with `trace.set_tracer_provider()`
and has the Junjo exporter attached. If the application already configures
OpenTelemetry, extend that setup rather than creating another provider. Workers,
application entrypoints, and provider diagnostics should call the same bootstrap.

Use `async with AsyncOpenAI() as client` for the client lifetime and pass that
client into the application-owned ModelDriver. Finish awaited Agent/Workflow
work, close the client, then call `tracer_provider.shutdown()` in `finally` to
drain queued spans. The example's
[main.py](https://github.com/mdrideout/junjo/blob/master/sdks/python/examples/junjo_openai_sdk/main.py)
shows that complete sequence. See the
[OpenInference instrumentor documentation](https://arize-ai.github.io/openinference/python/instrumentation/openinference-instrumentation-openai/)
for supported SDK versions and API operations.

### Understand the captured evidence

A representative native trace has both Junjo and provider evidence:

```text
Junjo Agent
├── model request
│   └── OpenInference LLM span (OpenAI SDK request)
├── lookup Tool
│   └── LookupOrderNode (application state update)
├── eligibility Tool
│   └── ReturnEligibilityWorkflow (conditional path and state updates)
└── subsequent model requests and final answer
```

Junjo records normalized model/Tool exchanges, typed application state, and the
Agent's separate private runtime state. OpenInference adds provider-level
request/response information, model attributes, timing, and reported usage.
Available fields depend on the API response, SDK and instrumentor versions,
streaming behavior, and capture settings. Missing usage is not evidence of zero
token consumption. Provider spans do not replace Junjo state transitions.

### Configure OpenInference content capture

OpenInference's `TraceConfig` controls its provider spans. To hide captured
inputs and outputs, replace the instrumentation call above with:

```python
from openinference.instrumentation import TraceConfig
from openinference.instrumentation.openai import OpenAIInstrumentor

OpenAIInstrumentor().instrument(
    tracer_provider=tracer_provider,
    config=TraceConfig(hide_inputs=True, hide_outputs=True),
)
```

Alternatively, set `OPENINFERENCE_HIDE_INPUTS=true` and
`OPENINFERENCE_HIDE_OUTPUTS=true` before initialization. `TraceConfig` also
supports finer controls for input/output messages, text, and input images; see
the [OpenInference capture configuration](https://arize-ai.github.io/openinference/python/openinference-instrumentation/#tracing-configuration).
The example leaves these at the instrumentor's defaults unless configured in
the environment, so its synthetic sample content is inspectable.

These controls do not redact Junjo's application Store snapshots, normalized
Agent transcript, or Tool results, and do not change what is sent to OpenAI.
Configure each capture surface according to
[State serialization and telemetry](#state-serialization-and-telemetry).

### Verify the trace in Studio

1. Run a representative request using the common bootstrap and note its trace
   ID. The example prints that ID and the configured Studio URL.
2. Find the trace in Studio. Confirm OpenInference LLM spans are children of
   Junjo model-request operations in that same trace.
3. Inspect the Agent's application state separately from its private runtime
   state, then open the Workflow's conditional path and state interval. A shared
   Store retains its identity across these execution views.
4. If evidence is absent, check initialization order and exporter errors, then
   verify the OTLP endpoint, TLS setting, and Studio **telemetry API key**.
   Successful model calls and local queue drains do not prove remote delivery.

The example's deterministic HTTP tests verify actual client instrumentation
and state evidence without credentials or paid calls. A live run followed by
Studio inspection verifies delivery for a particular deployment. Keep explicit
paid provider smoke tests in setup or diagnostics instead of repeating them on
every application startup.

### Distinguish the OpenAI client from the OpenAI Agents SDK

This setup uses Junjo as the Agent runtime and instruments the OpenAI **client**.
The [OpenAI Agents SDK integration](/docs/python/integrations/openai-agents/)
bridges a different Agent runtime's tracing, including its model operations,
into the application's provider. It is not required for native Junjo Agents.

Instrument a client once through the shared bootstrap. When combining runtimes,
identify which instrumentation already represents each model call before adding
another instrumentor; overlapping provider capture can produce duplicate model
evidence. Apply the external runtime's own content settings as well when using
its tracing bridge.

For other library choices, use the [examples and integrations index](/docs/examples-and-integrations/).

## How Junjo Uses OpenTelemetry

**What Gets Traced Automatically:**

- Workflow execution (start state, end state, graph structure)
- Agent execution (definition, normalized model/Tool operations, state,
  usage, limits, and terminal outcome)
- Individual node execution
- Subflow execution with parent relationships
- RunConcurrent concurrent execution
- State machine updates

**Native Junjo Instrumentation:**

Once an OpenTelemetry SDK provider and exporter are configured, native Junjo
executions emit their supported spans without adding tracing code to each Node.
Application code remains responsible for additional operations and for any
fields excluded or redacted from captured payloads.

```python
# Your workflow code stays the same
await my_workflow.execute()

# Junjo automatically creates spans with rich attributes
```

## Automatic Span Creation

When you execute a workflow, Junjo creates a hierarchy of OpenTelemetry spans:

```text
Workflow Span
├── Node Span (source)
├── Node Span
├── Subflow Span
│   ├── Node Span
│   └── Node Span
└── Node Span (declared sink)
```

Each span includes Junjo-specific attributes that provide workflow context.

### Agent hierarchy and ownership

An Agent is an executable owner span, not a synthetic Workflow. Model requests
and Tool calls are ordered operation spans owned by that Agent run:

```text
Agent
├── model request 1
├── tool lookup
│   └── Workflow                 (when the Tool invokes a Workflow)
│       └── Node
└── model request 2
```

An Agent invoked by a Workflow Node is physically and semantically nested
under that Node. A standalone Agent under a non-Junjo server span preserves the
physical OpenTelemetry parent but does not fabricate Junjo semantic-parent
attributes. Nested Agent owners each restart their own operation sequence,
private runtime Store revisions, usage aggregate, limits, and terminal evidence.
Application Store revisions continue across executions that share the same live
Store; each execution records its own application-state interval. See
[Store composition](/docs/python/agents/composition/).

Owner spans distinguish definition, run, and structural identity:

- `junjo.executable_definition_id` identifies the definition object;
- `junjo.executable_runtime_id` and `junjo.agent.runtime_id` identify the
  current run;
- `junjo.executable_structural_id` is the deterministic `agent_sha256`
  behavior fingerprint.

`junjo.parent_executable_*` records the nearest semantic Junjo owner when
one exists. Those values intentionally may skip an operation span: a Workflow
physically started inside a Tool is semantically parented by the Agent because
the Tool is not an executable definition owner.

Every Junjo executable span includes
`junjo.telemetry.contract_version`. This integer identifies the
language-independent contract used by SDK emitters and Studio consumers; it is
separate from the Python package version and from payload-specific schema
versions such as the execution graph snapshot's `v` field.

### Application execution correlation

Applications often need to connect one domain action to every Junjo
executable it caused without making a domain ID equal to a Workflow run ID or
an OpenTelemetry trace ID. Pass one immutable
[`ExecutionCorrelation`](/docs/python/api/junjo/executioncorrelation/) at the trusted top-level
execution boundary:

```python
from junjo import ExecutionCorrelation

result = await workflow.execute(
    correlation=ExecutionCorrelation(
        type="support.ticket",
        id=ticket.id,
    )
)
```

The value is inherited automatically by nested Workflow, Subflow, Node,
RunConcurrent, and Agent owner spans. A nested executable cannot replace an
active correlation with a different value. Junjo records the pair as
`junjo.correlation.type` and `junjo.correlation.id` on executable owner
spans. Model and Tool operation spans do not duplicate it because their owning
Agent is explicit.

Correlation remains diagnostic execution input. Junjo does not add it to
Store state, Tool dependencies, OpenTelemetry Baggage, or application
authorization. The application still passes its domain identity explicitly
where business behavior needs it, and it must revalidate any identity received
across a network boundary.

### Agent evidence and Store replay

The Agent owner contains its definition snapshot, normalized input, start/end
private runtime state and optional application state, aggregate usage, exact limits and counters, output when successful, and
one terminal outcome. Model operation spans contain the immutable request,
raw portable response candidate when available, validated normalized response,
descriptor identity, usage, ordinal, operation sequence, and state revision.
Tool operation spans similarly distinguish requested arguments, admitted
validated arguments, service result candidate, validated result, call identity,
ordinal, sequence, and before/after revisions.

Agent runtime and application state transitions use the same observable Store protocol as Workflows.
Each `set_state` event includes:

- `junjo.store.action` and a contiguous transition sequence;
- before/after revisions (no-op transitions do not advance revision);
- a portable RFC 6902 patch and its payload mode/policy;
- the physical Store identity.

Studio and conformance consumers collect events across the owner and its
operation spans, order them by transition sequence, replay from
`junjo.agent.state.start`, and require the result to equal
`junjo.agent.state.end`. The Agent action grammar exposes model start and
response, whole-batch admission, Tool start/result, and one terminal commit.
`junjo.store.reconstructable` is false only when complete replay cannot be
claimed, such as a failed terminal Store commit.

Application Store evidence is separate: `junjo.agent.application_store.id`
identifies the live Store and `junjo.agent.application_state.start/end` hold the
execution snapshots. Its revision and transition boundaries use the
`junjo.agent.application_store.*` prefix. Model and Tool state-revision fields
continue to refer to private Agent runtime state.

Contract 3 adds `transition.start` and `transition.end` to each Store boundary.
Studio reconstructs only events in `(start, end]`, even when another execution
uses the same Store. The normalized trace indexes each physical Store's
transitions once and attaches role-specific boundaries to each executable.
Sharing does not change span parentage. Missing events, including writers in
another trace, make the affected view incomplete. See
[composition and concurrency](/docs/python/agents/composition/#concurrency-and-state-evidence).
SDK and Studio must use the active telemetry contract together; older evidence
remains available as raw spans, with unsupported semantic annotations diagnosed.

All contract payload slots explicitly report `.mode` and `.policy`. The
SDK's core policy is `full` / `junjo.full.v1`; absence is never silently
interpreted as redaction. Unavailable model or Tool candidates instead carry
an explicit availability flag and reason such as `not_returned`,
`not_json_serializable`, `not_invoked`, or `cancelled`. Every full JSON
payload obeys the portable I-JSON boundary described in [Agents](/docs/python/agents/).

In Junjo AI Studio, begin diagnosis at the Agent owner: verify outcome,
termination reason, evidence completeness, and Store reconstruction. Then
follow operation sequence to the first failed/cancelled Model or Tool span and
inspect candidate-versus-validated payload slots. Semantic parent identities
show whether the Agent was invoked directly, by a Workflow Node, or around a
nested Workflow. Evidence-loss counters and non-full payload policies must be
shown as diagnostic limitations rather than treated as application behavior.

## Provider Lifecycle

Junjo AI Studio accepts OTLP traces. It does not currently accept OTLP metrics.
`JunjoOtelExporter` therefore gives you one component to attach to your
`TracerProvider`:

- `span_processor` for tracing

The exporter does not create a meter provider, metric reader, or periodic
metric-export worker. If your application exports metrics to another
OpenTelemetry platform, configure and own that independent metric pipeline in
the normal OpenTelemetry way.

It also exposes:

- `shutdown()` for wrapper-local shutdown of the Junjo-owned span processor
- `flush()` for manual immediate drain when you truly need it

Use `flush()` for targeted cases such as tests or short-lived scripts. It asks
the local batch processor to drain; OpenTelemetry does not propagate collector
acceptance through that result. Query Studio when you need proof of remote
delivery or persistence. Use `TracerProvider.shutdown()` for the normal
application lifecycle.

## Library Logging

Junjo emits library logs under the `junjo` logger hierarchy. Applications own
handlers, formatting, and log levels.

The main library loggers are:

- `junjo.workflow`
- `junjo.node`
- `junjo.run_concurrent`
- `junjo.telemetry`

Junjo does not install real log handlers of its own. If you want to see Junjo
execution diagnostics, configure logging in your application and opt in to the
`junjo` logger namespace.

```python
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s %(name)s %(message)s",
)
logging.getLogger("junjo").setLevel(logging.DEBUG)
```

With that configuration, Junjo emits debug-level execution progress through the
standard Python logging system without taking over your application's logging
setup.

Runtime log records include run-scoped correlation fields through standard
logging `extra` attributes when that execution context exists:

- `run_id`
- `executable_definition_id`
- `executable_runtime_id`
- `span_type`

Applications using structured logging handlers can capture those fields
directly from the log record without parsing log message text.

Execution failures are logged at the owning workflow or subflow boundary so one
propagated failure produces one library-owned error log instead of multiple
stack traces from each nested execution layer.

Exporter-local warning logs under `junjo.telemetry` also include the OTLP
`endpoint` on the log record so operational failures can be tied back to the
destination that failed.

## Choosing an OpenTelemetry Exporter

Junjo works with any OpenTelemetry-compatible platform. Choose based on your needs:

### 1. Junjo AI Studio (Recommended for AI Workflows)

A telemetry and evaluation observation suite with:

- queryable execution chronology for coding-agent investigation;
- recorded Workflow graphs, Agent operation timelines, and state diffs;
- shared evaluation datasets and comparable Runs linked to exact evidence; and
- browser views so humans can inspect the records behind an agent's findings.

See [Junjo Ai Studio](/docs/studio/overview/) for complete setup.

The application must reach the ingestion endpoint and authenticate with its
telemetry API key. Within the supported Compose deployment's network, the
service hostname is `junjo-ai-studio-ingestion`. A separate Compose project
must explicitly join the correct network or use a reachable published endpoint;
its own `localhost` refers to that application container. Use
`localhost:26155` only when the application runs on the Studio host and that
port is published there. See the [deployment guide](/docs/studio/deployment/).

```python
from junjo.telemetry.junjo_otel_exporter import JunjoOtelExporter

junjo_exporter = JunjoOtelExporter(
    endpoint="junjo-ai-studio-ingestion:26155",  # Same Compose network
    api_key=api_key,
    insecure=True
)
tracer_provider.add_span_processor(junjo_exporter.span_processor)
```

For production, use the public Junjo AI Studio ingestion host and TLS:

```python
from junjo.telemetry.junjo_otel_exporter import JunjoOtelExporter

junjo_exporter = JunjoOtelExporter(
    endpoint="ingestion.example.com:443",
    api_key=api_key,
    insecure=False
)
tracer_provider.add_span_processor(junjo_exporter.span_processor)
```

### 2. Jaeger

General-purpose distributed tracing, good for microservices integration.

```python
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.trace.export import BatchSpanProcessor

jaeger_exporter = OTLPSpanExporter(
    endpoint="http://jaeger:4317",
    insecure=True
)
tracer_provider.add_span_processor(BatchSpanProcessor(jaeger_exporter))
```

### 3. Grafana/Tempo

Metrics + traces in one platform, good for production monitoring.

```python
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.trace.export import BatchSpanProcessor

tempo_exporter = OTLPSpanExporter(
    endpoint="http://tempo:4318/v1/traces",
    headers={"Authorization": "Bearer <token>"}
)
tracer_provider.add_span_processor(BatchSpanProcessor(tempo_exporter))
```

### 4. Honeycomb, Datadog, New Relic, etc.

Enterprise observability platforms with full-featured APM.

```python
# Example: Honeycomb
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.trace.export import BatchSpanProcessor

honeycomb_exporter = OTLPSpanExporter(
    endpoint="https://api.honeycomb.io/v1/traces",
    headers={"x-honeycomb-team": "<api-key>"}
)
tracer_provider.add_span_processor(BatchSpanProcessor(honeycomb_exporter))
```

## Using Multiple Exporters

You can send telemetry to multiple platforms simultaneously:

```python
from junjo.telemetry.junjo_otel_exporter import JunjoOtelExporter
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.resources import Resource
from opentelemetry import trace

# Create resource
resource = Resource.create({"service.name": "my-workflow"})

# Set up tracer provider
tracer_provider = TracerProvider(resource=resource)

# Add Junjo AI Studio exporter
junjo_exporter = JunjoOtelExporter(
    endpoint="junjo-ai-studio-ingestion:26155",  # Same Compose network
    api_key=junjo_api_key,
    insecure=True
)
tracer_provider.add_span_processor(junjo_exporter.span_processor)

# Also send to Jaeger
jaeger_exporter = OTLPSpanExporter(endpoint="http://jaeger:4317")
tracer_provider.add_span_processor(BatchSpanProcessor(jaeger_exporter))

# Set as global tracer provider
trace.set_tracer_provider(tracer_provider)
```

## Junjo's Custom Span Attributes

Junjo adds its contract attributes to native Junjo spans. External spans keep
their own instrumentation conventions. Both can use the same OTLP exporter:

Failed Workflow, Subflow, Node, concurrent-execution, Agent, model-request, and
Tool spans also follow the standard OpenTelemetry error contract in addition
to the Junjo-specific fields below:

- `error.type` is set to the exception class name on failed spans.
- span status is set to `Error`.
- Junjo constructs the standard `exception` span event fields from its
  non-throwing portable diagnostic projection, so hostile exception formatting
  cannot replace the execution outcome or produce invalid telemetry text.

Cancelled spans use Junjo-specific cancellation attributes instead of the
standard error fields:

- `junjo.cancelled` is set to `true`.
- `junjo.cancelled_reason` describes why the operation was cancelled.

Cancelled spans do not set `error.type` and are not marked with `Error`
status unless they actually fail.

## State Serialization And Telemetry

Junjo intentionally records rich workflow state in telemetry by default. This
is a debugging-oriented design choice: many AI workflows need full prompts,
tool inputs, tool outputs, and intermediate state to be visible in traces.

Detailed execution evidence can be valuable production data. Self-hosting
Junjo AI Studio lets you choose the infrastructure and storage backing its
persistent data directory, and apply encryption, network isolation, access
controls, and backup practices consistent with your production environment.
You can protect captured evidence to the same security standard as the
application data it describes. The
[deployment guide](/docs/studio/deployment/#preserve-the-experiment-history)
explains the persistent storage arrangement.

Choose what to capture alongside where and how that evidence will be stored
and accessed. Capture controls differ between execution types:

| Execution surface | Capture control |
| --- | --- |
| Application Store state (Workflow or Agent) | State-model serialization controls the captured state representation, as described below. |
| Native Junjo Agent runtime and operations | Instrumentation records full normalized payloads. The current public Agent API does not expose a selective capture policy; application-state serialization is not a general Agent transcript redaction API. |
| OpenInference provider spans | The instrumentor's `TraceConfig` or environment settings control provider content. See [OpenInference content capture](#configure-openinference-content-capture); these settings do not suppress native Junjo telemetry. |
| OpenAI Agents integration | Source tracing settings govern what the bridge receives; they do not suppress nested native Junjo telemetry. See the [integration's capture guidance](/docs/python/integrations/openai-agents/#treat-content-capture-as-a-privacy-choice). |
| Other application spans | Capture is governed by the application's instrumentation and exporters. |

Application Store telemetry is derived from your state model's normal Pydantic
serialization:

- `junjo.workflow.state.start` and `junjo.workflow.state.end` use the
  serialized state JSON
- `junjo.agent.application_state.start` and `junjo.agent.application_state.end`
  use the Agent's application-state serialization
- `junjo.state_json_patch` is built from serialized before/after state dumps

This means your state model controls what appears in OpenTelemetry state
payloads. If you want to exclude, redact, or truncate fields for telemetry,
shape that behavior in your state model serialization.

Junjo applies those serialization choices only when producing telemetry
payloads. Runtime state transitions still use the state object's field values,
so excluded or serialized fields are not removed or rewritten by later
`set_state` calls.

This does **not** apply to `junjo.workflow.execution_graph_snapshot`, which
is generated from the compiled graph rather than from state serialization.
See [Junjo Ai Studio](/docs/studio/overview/) for the AI Studio identity and execution graph
snapshot contract.

### Controlling Telemetry State Payloads

If you need to keep a field in runtime state but remove it from serialized
telemetry payloads, exclude it from Pydantic serialization:

```python
from pydantic import Field
from junjo import BaseState

class ChatWorkflowState(BaseState):
    user_message: str
    llm_response: str | None = None
    raw_api_key: str | None = Field(default=None, exclude=True)
```

In this example, `raw_api_key` remains available in runtime state, but it is
omitted from serialized OpenTelemetry state snapshots and JSON patches.

If you want to keep a field but truncate or reshape it for telemetry, use a
serializer on the state model:

```python
from pydantic import field_serializer
from junjo import BaseState

class PromptWorkflowState(BaseState):
    prompt: str
    final_answer: str | None = None

    @field_serializer("prompt")
    def serialize_prompt_for_telemetry(self, value: str) -> str:
        if len(value) <= 2000:
            return value
        return value[:2000] + "...[truncated]"
```

In this example, runtime state still holds the full prompt, but Junjo's
OpenTelemetry state fields and patches use the truncated serialized form.

### Hook Events Use Copied State Objects

Hook event state payloads are separate from OpenTelemetry serialization.

- OpenTelemetry state fields use serialized state from your model
- hook `event.state` values use a copied in-memory state object

So excluding or truncating a field for telemetry serialization does **not**
automatically remove it from `event.state` inside hook callbacks.

### Application-owned artifact references

An application-owned artifact reference can replace embedded content in
observable input, output, or state. For example, a typed reference can carry an
artifact ID, content digest, and media type while the application retains the
bytes in its artifact storage. The application owns artifact storage,
authorization, retrieval, and retention. The reference remains ordinary
application data; it does not automatically select a telemetry capture mode or
cause Studio to retrieve the artifact.

### Workflow/Subflow Span Attributes

```python
{
    "junjo.span_type": "workflow" | "subflow",
    "junjo.executable_definition_id": "<workflow-definition-id>",
    "junjo.executable_runtime_id": "<workflow-run-id>",
    "junjo.executable_structural_id": "<graph-structural-id>",
    "junjo.enclosing_graph_structural_id": "<graph-structural-id>",
    "junjo.workflow.state.start": "<initial-state-json>",
    "junjo.workflow.state.end": "<final-state-json>",
    "junjo.workflow.execution_graph_snapshot": "<execution-graph-snapshot-json>",
    "junjo.workflow.node.count": 5,
    "junjo.workflow.store.id": "<store-id>",

    # Subflow only:
    "junjo.parent_executable_definition_id": "<parent-workflow-definition-id>",
    "junjo.parent_executable_runtime_id": "<parent-executable-runtime-id>",
    "junjo.parent_executable_structural_id": "<parent-executable-structural-id>",
    "junjo.workflow.parent_store.id": "<parent-store-id>"
}
```

### Node Span Attributes

```python
{
    "junjo.span_type": "node",
    "junjo.executable_definition_id": "<node-definition-id>",
    "junjo.parent_executable_definition_id": "<parent-workflow-or-subflow-definition-id>",
    "junjo.executable_runtime_id": "<node-runtime-id>",
    "junjo.executable_structural_id": "<node-structural-id>",
    "junjo.parent_executable_runtime_id": "<parent-executable-runtime-id>",
    "junjo.parent_executable_structural_id": "<parent-executable-structural-id>",
    "junjo.enclosing_graph_structural_id": "<graph-structural-id>"
}
```

### RunConcurrent Span Attributes

```python
{
    "junjo.span_type": "run_concurrent",
    "junjo.executable_definition_id": "<run-concurrent-definition-id>",
    "junjo.parent_executable_definition_id": "<parent-workflow-or-subflow-definition-id>",
    "junjo.executable_runtime_id": "<run-concurrent-runtime-id>",
    "junjo.executable_structural_id": "<run-concurrent-structural-id>",
    "junjo.parent_executable_runtime_id": "<parent-executable-runtime-id>",
    "junjo.parent_executable_structural_id": "<parent-executable-structural-id>",
    "junjo.enclosing_graph_structural_id": "<graph-structural-id>"
}
```

These attributes enable:

- Filtering spans by workflow or node type
- Correlating nodes with their parent workflows
- Viewing state changes over time
- Understanding graph structure

## Production Junjo AI Studio Exporter

For production, configure `JunjoOtelExporter` with the public OTLP/gRPC target
and TLS:

```python
junjo_exporter = JunjoOtelExporter(
    endpoint="ingestion.example.com:443",
    api_key=api_key,
    insecure=False
)
```

## Advanced Configuration

### Sampling

Sampling reduces telemetry volume by intentionally discarding traces. For
local evaluation and diagnosis, retain the executions you need to compare.
Sampling can leave an Attempt's evidence pending or unavailable and can prevent
state reconstruction; a result record does not restore a discarded trace.
Choose production sampling separately based on the evidence you need to keep.

For a workload where retaining only a sample is acceptable:

```python
from opentelemetry.sdk.trace.sampling import TraceIdRatioBased

# Sample 10% of traces
tracer_provider = TracerProvider(
    resource=resource,
    sampler=TraceIdRatioBased(0.1)
)
```

### Custom Resource Attributes

Add custom attributes to all spans:

```python
resource = Resource.create({
    "service.name": "my-workflow",
    "service.version": "2.0.0",
    "deployment.environment": "production",
    "team.name": "ai-team",
    "custom.attribute": "value"
})
```

### Context Propagation

Propagate trace context across services using the format agreed by both ends.
The OpenTelemetry default is W3C Trace Context. If your environment explicitly
uses B3, install `opentelemetry-propagator-b3` before this configuration:

```python
from opentelemetry import propagate
from opentelemetry.propagators.b3 import B3MultiFormat

# Use B3 propagation format
propagate.set_global_textmap(B3MultiFormat())
```

## What You See in Your Platform

When viewing Junjo traces in your observability platform, you'll see:

**Span Hierarchy:**

- Clear parent-child relationships between workflows and nodes
- Nested subflows with their internal nodes
- Concurrent execution timing (RunConcurrent)

**Custom Attributes:**

- All `junjo.*` attributes for filtering and analysis
- State snapshots at workflow start/end
- Graph structure for understanding workflow design

**Timing Derived from Traces:**

- Node execution duration
- Workflow total duration
- Concurrent execution overlap

**Platforms without Junjo AI Studio** will receive all this data but display it in their standard trace viewer. **Junjo AI Studio** provides specialized visualization for these workflow-specific attributes.

## Troubleshooting

### No spans appearing

`trace.get_tracer()` returns an object even when no recording provider is
configured. Check a real span and then verify its delivery:

```python
from opentelemetry import trace

# Run after init_telemetry() has installed the provider.
with trace.get_tracer("my-app.telemetry-check").start_as_current_span(
    "junjo.telemetry.check"
) as span:
    span.set_attribute("diagnostic.purpose", "verify Studio delivery")
    context = span.get_span_context()
    print("recording:", span.is_recording())
    print("trace_id:", f"{context.trace_id:032x}")
    print("span_id:", f"{context.span_id:016x}")

tracer_provider.force_flush()
```

A recording span proves local instrumentation is active, not that Studio
received it. Open **Logs** in Studio and locate the printed trace ID. Then
run a real Workflow or Agent and verify its native execution and state evidence.
If the diagnostic span is not recording, inspect provider installation and
sampling. If it records locally but is absent remotely, check the actual
endpoint, TLS mode, telemetry credential, and exporter logs. Batching and
indexing can delay visibility; `force_flush()` is not a remote-delivery receipt.

### Missing Junjo attributes

- Native Junjo execution adds its contract attributes when the configured provider records the span; a generic external span does not acquire native graph or state semantics
- Verify you're viewing the correct span (workflow vs node)
- Check your platform supports custom attributes

### Performance impact

- Measure overhead with your application's payload sizes, span volume, and concurrency; there is no universal percentage.
- `JunjoOtelExporter` uses a batch span processor. Avoid forcing a flush after each request.
- Large prompts, responses, and state histories increase serialization, transport, and storage work. Apply an intentional capture policy and document the resulting evidence limits.
- Use sampling only where incomplete execution coverage is acceptable.

## Next Steps

- Set up [Junjo Ai Studio](/docs/studio/overview/) for AI workflow-specific debugging
- Explore [Visualizing Workflows](/docs/python/workflows/visualization/) for static diagrams
- Learn about [Concurrency](/docs/python/workflows/concurrency/) to understand concurrent execution traces
- Use [evaluation datasets and runs](/docs/python/evaluation/) to compare outcomes with their traces
- Follow [recursive self improvement](/docs/recursive-self-improvement/) to turn a recorded failure into a measured code change

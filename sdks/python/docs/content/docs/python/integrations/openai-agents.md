---
title: "OpenAI Agents SDK Integration"
description: "Use Junjo Workflows, Agents, telemetry, and evaluation inside an OpenAI Agents SDK application."
---

Junjo's OpenAI Agents SDK integration is additive. The OpenAI Agents SDK keeps
owning its Agent loop, sessions, handoffs, guardrails, models, and framework
state. Junjo supplies its native stateful Workflows and bounded Agents as
explicit function tools, sends both runtimes through one application-owned
OpenTelemetry pipeline, and lets the same application expose any useful
boundary to Junjo Evaluation.

Install the optional integration without adding OpenAI dependencies to
applications that do not need them:

```bash
uv add "junjo[openai-agents]"
```

The integration lives in `junjo.plugins.openai_agents`. Importing that module
does not instrument the process or configure telemetry.

## Runtime shape

```text
OpenAI Agent runner
  -> OpenAI function-tool span
     -> native Junjo Workflow or Junjo Agent
        -> Junjo Node, Store, model, and Tool spans
  -> OpenAI model-client span
  -> one application-owned OpenTelemetry provider and exporter
     -> Junjo AI Studio OTLP ingestion
```

External spans retain standard `gen_ai.*` attributes. Native Junjo executions
retain their existing semantic identities and `junjo.*` attributes. Studio
shows both in the ordinary full trace; it does not relabel an external Agent as
a native Junjo Agent.

## Own telemetry once

Construct the OpenTelemetry SDK `TracerProvider`, resource identity, processors,
and exporters in the application's ordinary process-lifetime telemetry
bootstrap. Pass that same provider to `instrument_openai_agents`, retain the
returned integration handle, and close the handle before shutting down the
provider.

The helper wraps the OpenAI Agents SDK's active first-party tracing provider
and mirrors each source Trace and Span into the supplied OpenTelemetry
provider. It does not patch an HTTP client, replace the supplied provider,
or shut down application telemetry. The original OpenAI provider remains
responsible for its processors, including any application-selected hosted
trace export. Closing the integration restores that exact provider.

An application that wants Studio to be its only tracing destination can use
the OpenAI Agents SDK's ordinary processor configuration before installing
the bridge. Junjo does not silently remove or configure another destination,
and Studio never reads or copies data from the OpenAI trace dashboard.

## Treat content capture as a privacy choice

The bridge preserves the source tracing payload. OpenAI Agents SDK
`RunConfig.trace_include_sensitive_data` therefore owns whether model inputs,
outputs, function arguments, and results are available to copy into Studio.
The upstream default is `True`; set it to `False` when those values should not
leave the application process. Captured values may contain user data, source
code, credentials, or other sensitive content, so Studio access and retention
must follow the same policy as the application data.

Junjo never serializes the OpenAI tracing API key. It records only whether one
was configured.

## Expose native Junjo execution as tools

Use `workflow_as_tool` for a fresh native Workflow invocation and
`agent_as_tool` for a fresh native Junjo Agent invocation. Application code
still owns:

- the Pydantic input contract;
- the OpenAI function-tool name and description;
- construction of fresh invocation state and dependencies;
- projection of the Junjo execution result into the tool response; and
- invocation-scoped cleanup.

These adapters deliberately do not create a generic executable protocol,
share Stores between runtimes, hide domain dependencies, or change failure and
cancellation ownership. The OpenAI runner sees an ordinary framework-native
function tool. The nested Junjo execution remains a complete native execution.

An OpenAI Agent may call both a Junjo Workflow and a Junjo Agent. Junjo Agent
remains the native opinionated Agent option for applications that do not need
an external outer runtime.

## Evaluate the outer Agent or the native boundaries

The optional `OpenAIAgentTarget` runs a real outer OpenAI Agent through the
application's normal construction path. It captures the exact standard
`invoke_agent` span for the declared Agent name and binds that span as the
Attempt's evidence. It fails clearly if the exact span is missing or
ambiguous; it does not substitute a nearby trace.

The same `EvaluationHarness` may also declare native Junjo Workflow, Agent, and
Node targets. Their evidence remains the semantic Junjo execution reference.
This allows one locked dataset to measure the user-visible outer Agent or more
focused native boundaries without confusing their identities.

Studio stores a discriminated evidence reference:

- `junjo_execution` for native Workflow, Subflow, and Agent evidence; or
- `otel_span` for an exact standard external span.

Both kinds use the same binary evaluation result contract and the same `View
spans` experience. Dataset, Case, Run, and Attempt IDs remain the stable
evaluation identities; trace and span IDs are physical evidence pointers.

Use the installed `junjo-evaluation` coding-agent skill to turn a product
quality objective into datasets, runs, comparisons, and trace analysis. The
optional integration skill is discoverable without a Junjo source checkout:

```bash
junjo eval skill path --name junjo-openai-agents
```

## Current telemetry coverage

Junjo translates every concrete SpanData type exposed by the validated OpenAI
Agents SDK version. A contract test fails when upstream adds a new concrete
type until Junjo deliberately maps and documents it. Known source types get
queryable semantic projections plus a complete, versioned JSON source payload;
an unexpected source type is retained through a generic raw-payload fallback
rather than dropped.

| OpenAI Agents activity | Current OpenTelemetry representation |
| --- | --- |
| Runner workflow | `invoke_workflow` span plus complete workflow Trace payload |
| Agent invocation | `invoke_agent` span plus Agent configuration and metadata |
| Function tool call | `execute_tool` span plus arguments, result, and MCP metadata |
| Generation or Responses model call | `chat` span plus source input, output/response model, configuration, and usage; the source discriminator distinguishes `generation` from `response` |
| Nested Junjo Workflow, Agent, Node, Store, and operation | Existing native Junjo telemetry inside the active tool context |
| Handoff, guardrail, task, turn, MCP tool listing, speech, transcription, and custom spans | Dedicated source-type span with complete versioned source payload |

The versioned integration attributes are defined in the repository telemetry
contract. Studio recognizes the marker before applying OpenAI-specific icons
or details, so unrelated applications that happen to use the same GenAI
operation names are not mislabeled.

## Observed deterministic local baseline

The previous third-party-instrumentor baseline is obsolete. The current
first-party bridge was measured with the small deterministic example. These
numbers are regression evidence for that fixture; they are not product limits
or capacity claims.

| Measurement | Native Junjo spans only | First-party bridge enabled |
| --- | ---: | ---: |
| Spans per deterministic run | 4 | 23 |
| OTLP protobuf bytes per run | 10,382 | 36,574 |
| Median deterministic run time | 47.63 ms | 50.84 ms |
| CPU time per deterministic run | 10.25 ms | 10.85 ms |

Fifty concurrent deterministic runs produced 50 separate source traces and 50
separate OpenTelemetry traces. The live Compose validation produced the same
23-span mixed tree in Studio and exposed full scripted model and tool inputs
and outputs through the structured source-data view.

Real payload cost is proportional to the source content captured. Repeated-run
and concurrent-run lifecycle tests guard against leaked Junjo-owned state and
cross-run evidence. No Studio ingestion, batching, hot/cold storage, or query
architecture changes for this integration.

## Run the canonical example

[`base_openai_agents`](https://github.com/mdrideout/junjo/tree/master/sdks/python/examples/base_openai_agents)
is deterministic and does not need an OpenAI API key. It proves:

- one outer OpenAI Agent;
- a native Junjo Workflow tool;
- a native Junjo Agent tool;
- one mixed trace with standard and native spans;
- direct native and outer-Agent evaluation targets; and
- exact span-evidence navigation in Studio.

Replace its scripted model with the application's real OpenAI Agents model
without changing Junjo's composition, telemetry, or evaluation ownership.

For the exact public types and signatures, use the generated API reference for
`junjo.plugins.openai_agents` and
`junjo.plugins.openai_agents.evaluation`. For the architectural boundaries,
see ADR 0015 in the Junjo repository.

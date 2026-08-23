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

The helper installs the official OpenTelemetry OpenAI Agents and OpenAI client
instrumentors. It does not replace or shut down the supplied provider. If the
official instrumentors are already active, Junjo preserves them rather than
installing a duplicate. Because an active instrumentor already owns its
provider and OpenAI native-export policy, Junjo cannot retroactively change
those choices; configure one owner during startup.

OpenAI's own hosted trace export remains enabled by default. An application may
explicitly disable that native export when it wants OpenTelemetry to be the
only tracing destination. Junjo AI Studio never reads or copies data from the
OpenAI trace dashboard.

## Treat content capture as a privacy choice

The official GenAI instrumentation does not capture prompt and response
content by default. Enabling
`OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT` can place messages, tool
arguments, and results in spans. Those values may contain user data, source
code, credentials, or other sensitive content. Choose the setting explicitly
for each deployment and apply the same access-control and retention policy as
the application data.

The deterministic repository example enables span-only content capture so its
local trace is inspectable. That is an example policy, not a production
default imposed by Junjo.

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

Coverage follows the official instrumentors resolved by the optional extra.
Junjo does not maintain a second copy of spans they already emit.

| OpenAI Agents activity | Current OpenTelemetry representation |
| --- | --- |
| Runner workflow | Standard `invoke_workflow` span |
| Agent invocation | Standard `invoke_agent` span |
| Function tool call | Standard `execute_tool` span with optional arguments and result content |
| OpenAI Chat Completions or Responses model call | Standard model-client span from the official OpenAI client instrumentor |
| Nested Junjo Workflow, Agent, Node, Store, and operation | Existing native Junjo telemetry inside the active tool context |
| Handoff, guardrail, generation/response callback, speech, transcription, or arbitrary custom OpenAI trace span | Not separately translated by the current official OpenAI Agents instrumentor when no stable GenAI semantic convention exists |

The last row is a known visibility limit, not a reason to invent Junjo-specific
duplicates. Junjo will add a narrow companion representation only when a
material application use case and stable semantics justify it.

## Observed deterministic local baseline

The 2026-08-18 validation used the built Junjo 0.66.0 wheel, OpenAI Agents
0.21.1, OpenTelemetry Python 1.44.0, Python 3.12.9 on Apple Silicon macOS, and
the local Studio 0.82.1 Compose stack. These are observations from the small
offline example, not product limits or capacity claims.

| Measurement | Observed value |
| --- | ---: |
| Spans per ordinary outer-Agent run | 8 |
| OTLP protobuf bytes with `NO_CONTENT` | 11,314 bytes |
| OTLP protobuf bytes with `SPAN_ONLY` | 11,523 bytes |
| Peak example-process memory across 10 runs | about 145 MiB |
| Retained traced-allocation delta after 10 runs | about 529 KiB |
| One 8-span OTLP force-flush round trip | 16.78 ms |
| Trace query availability after flush | 43.96 ms |
| Recent-cold trace query after the ingestion flush interval | 28.79 ms |

The content-enabled fixture added 209 serialized bytes because its prompts and
tool values are intentionally small. Real payload cost is proportional to the
application content captured. The retained-allocation observation includes
normal Python and upstream SDK caches; it is not evidence of a steady-state
memory ceiling. Repeated-run lifecycle tests remain the guard against leaked
Junjo-owned registrations or run-scoped resources. No Studio ingestion,
batching, hot/cold storage, or query architecture changed for this integration.

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

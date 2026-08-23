---
name: junjo-openai-agents
description: Add Junjo's optional OpenAI Agents SDK integration to an application. Use when a coding agent needs to install junjo[openai-agents], expose a native Junjo Workflow or Agent as an OpenAI function tool, send standard OpenAI Agent and nested Junjo spans through one application-owned OpenTelemetry provider, declare an outer OpenAI Agent evaluation target, or validate the mixed trace in Junjo AI Studio.
---

# Junjo + OpenAI Agents

Integrate Junjo additively inside the application repository. The OpenAI
Agents SDK remains the outer Agent runtime. Junjo remains the native,
opinionated Workflow, state, concurrency, telemetry, and evaluation layer.

## Boundaries

- Install the optional extra with `junjo[openai-agents]`. Do not add OpenAI
  Agents dependencies to Junjo's default runtime path.
- Use the public `junjo.plugins.openai_agents` module. Do not copy adapters or
  instrumentation into the application.
- Keep telemetry bootstrap application-owned and process-lifetime. Reuse the
  application's existing OpenTelemetry SDK `TracerProvider` and exporter.
- Instrument explicitly during application startup and close the returned
  integration handle during shutdown. Never instrument at module import time.
- Treat OpenAI Agent spans as standard OpenTelemetry GenAI evidence. Do not
  rewrite them into fake Junjo Agent spans or send them through a separate
  proprietary ingestion path.
- Keep native Junjo Workflows and Agents semantically native. Their tool
  adapters translate inputs, outputs, and invocation cleanup; they do not
  merge execution identities or lifecycle ownership.
- Preserve separate Studio credentials: the application telemetry API key
  exports OTLP; the developer access token operates datasets and evidence.

## Inspect before changing

Read the application's instructions, dependency manifest, telemetry startup,
shutdown path, Agent construction, Junjo definitions, and evaluation harness.
Inspect the installed public API and docs rather than guessing signatures.

Determine how the application configures OpenAI Agents tracing processors.
Junjo wraps the active first-party tracing provider and preserves its
processors and export policy. Reuse the application's OpenTelemetry provider
and make one owner responsible for shutdown.

## Compose explicit tools

Expose a fresh native Junjo Workflow or Junjo Agent invocation through the
framework-specific adapter that matches it. Map:

- one Pydantic input contract;
- one stable function-tool name and useful description;
- construction of fresh invocation state for each call;
- projection of the native execution result into the tool result; and
- invocation-scoped cleanup when application resources require it.

Do not build a generic plugin registry or universal executable abstraction.
Keep domain dependencies and result projection visible in application code.
The same outer OpenAI Agent may call both native Junjo Workflows and native
Junjo Agents.

## Connect telemetry

Install Junjo's first-party OpenAI Agents tracing bridge using the
application's provider. It translates the SDK's native Trace and Span objects,
including complete versioned source payloads, while Junjo native execution
emits its existing semantic Workflow, Agent, Node, Store, and operation spans
into that same provider.

Choose OpenAI's native hosted trace processors deliberately; Junjo AI Studio
does not require that dashboard. Choose the OpenAI Agents SDK
`RunConfig.trace_include_sensitive_data` policy deliberately because source
payloads may contain user data or secrets. Never put tracing API keys into span
attributes.

Validate one mixed trace in Studio:

1. the outer standard OpenAI Agent span is present;
2. each standard tool-call span is present;
3. nested Junjo Workflow or Agent owner spans are present beneath the tool
   invocation;
4. nested Node, Store, and operation evidence remains navigable; and
5. Studio labels standard operations without pretending they are native Junjo
   executions.

## Add evaluation only when requested

If the application already has a Junjo `EvaluationHarness`, declare the outer
OpenAI Agent with the optional evaluation target. The factory must construct a
fresh invocation, the expected Agent name must match the standard
`invoke_agent` span, and the projector must return the actual subject to judge.

The target records an exact OpenTelemetry span reference. Native Junjo targets
continue to record semantic Junjo execution references. Do not fabricate a
nearby trace or span when exact evidence is unavailable.

Use the `junjo-evaluation` skill for dataset design, execution, comparison,
failure analysis, and improvement loops. This skill owns integration setup;
the evaluation skill owns operating evaluations from product intent.

## Validate

Run the owning application tests and type/lint checks. Exercise a real outer
Agent call with every added native tool. Confirm clean telemetry startup and
shutdown, inspect the mixed trace in Studio, and—when an outer target was
added—run one Studio-backed evaluation and open its exact `View spans` link.

Use the installed Python documentation and the canonical
`base_openai_agents` example as the detailed reference. Keep this skill focused
on decisions and ownership rather than duplicating function signatures,
environment-variable catalogs, or Studio routes.

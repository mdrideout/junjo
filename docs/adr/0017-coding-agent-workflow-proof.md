# ADR 0017: Coding-agent workflow proof

- Status: Accepted for the first-pass proof
- Date: 2026-09-20
- Owners: Junjo platform

## Context

A coding-agent session can supply the reasoning for a structured Junjo
workflow. The user wants native Codex subagents to perform those steps using
their existing authenticated host, with optional execution diagnostics in
Studio. An application that calls an LLM SDK would not prove this behavior.

## Decision

`apps/coding-agents` owns a separately packaged local MCP bridge and a Codex
plugin. The existing Python SDK and Studio retain their boundaries and native
telemetry contract. This is a product integration proof, not a new language SDK
or a universal host abstraction.

The bridge executes a real Junjo Workflow. A Node publishes typed work and
awaits a result. The coding host reads that work, reasons, and submits a
schema-validated result through MCP. The Node resumes, updates its Store, and
the native Graph evaluates its Condition and selects the next Node. Each
native worker receives a fresh Workflow and Store. Junjo does not call model
APIs or start replacement reasoning agents.

A batch owns a root integration span. Worker wrappers parent native Workflow
spans, which retain their normal Node, state, and definition evidence. Capture
is off by default. A valid unsampled parent also suppresses native SDK spans
for executions with capture disabled.

Codex host export must be configured separately, before the host starts. The
plugin cannot intercept its host's private model client or retrofit telemetry
into an already running session. The first adapter accepts Codex OTLP/HTTP JSON
traces and tool-result logs on loopback. Logs are transient correlation input;
Studio still receives only OTLP traces, as required by ADR 0012.

For each accepted step, a random completion receipt joins its successful host
tool result to source span ancestry. The adapter projects the actual
`responses_websocket.stream_request` from that sampling request under the
waiting Junjo Node. The projected span uses source timestamps and links to the
original trace/span IDs. It is explicitly attributed as a projection and has
no fabricated native `junjo.span_type`. Host text unrelated to that receipt is
not retained. This extends ADR 0015's external-provenance principle without
changing its OpenAI Agents SDK integration.

## Proof scope and limits

The example runs two native Codex workers against correct and buggy parity
functions. It demonstrates Workflow, Graph, Node, Condition, Store, typed
results, concurrent isolated executions, and model evidence in Studio.

The current adapter recognizes source operations observed in Codex 0.144.3.
Its coverage is the model request submitting each accepted step. Intermediate
reasoning/tool requests, failed unsubmitted steps, complete prompts/responses,
per-request tokens, and other host transports are not established by this
proof. Zero captured model spans is missing evidence, not success. A tool
result must be printed intact, and each next step must be reasoned about in a
new model response. Source timing may extend beyond a Node's interval because
the host streams tools before its request fully closes; preserve that fact.

State and compact correlation metadata are process-local and released when the
bridge exits. The bridge is for one trusted local developer. This decision adds
no hosted multiuser service, durable resume, universal adapter framework,
automatic desktop telemetry setup, or production release pipeline. Cursor,
Antigravity, and other transports require their own source-evidence validation.

## Validation

Unit tests prove native branching and Store isolation, capture suppression,
typed handoff validation, cancellation, delayed source parents, deduplication,
and rejection of unmatched/pre-handoff/unknown source evidence. A separate live
run must prove native subagent sessions, four attributable model requests, and
unchanged Studio ingestion and presentation. Synthetic fixtures alone cannot
establish host instrumentation.

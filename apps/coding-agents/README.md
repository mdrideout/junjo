# Junjo for Coding Agents — first-pass proof

Native Codex workers supply the reasoning for real Junjo Workflows. This
component contains no LLM API client. The installed plugin tells Codex how to
use a local MCP bridge; the Python SDK owns graph traversal, validation, and
state. Diagnostic capture is optional and off by default.

[Verified live on 2026-09-20](evidence/2026-09-20-codex-proof.json): two native
Codex subagents, four attributable model spans, and all 13 execution spans
retrieved from Studio with complete Workflow/Store integrity. The trace tree,
graph branches, model diagnostics, and final state were also checked in the UI.

## The observable example

Ask Codex to review two tiny `is_even(n)` functions using two native subagents.
One fixture incorrectly checks `n % 2 == 1`; the other checks `== 0`. Each worker
inspects its snippet, then the Junjo Condition selects a correction or
correctness explanation. Workers have separate Stores and Workflow run IDs.

```text
Review example functions                    integration root
├─ Codex worker (buggy)                      external worker wrapper
│  └─ FunctionReview                        native Workflow / Graph / Store
│     ├─ InspectFunction                    native Node
│     │  └─ Codex model request             linked host request evidence
│     └─ ExplainCorrection                  selected by BugFound Condition
│        └─ Codex model request
└─ Codex worker (correct)
   └─ FunctionReview
      ├─ InspectFunction
      │  └─ Codex model request
      └─ ExplainCorrectness
         └─ Codex model request
```

Native SDK spans additionally carry graph definitions, Store transitions, and
condition evidence. There is no native Junjo Agent in this example: Codex owns
the agent loop. External wrappers and model spans do not claim Junjo identity.

## Local setup

Follow [Studio's testing runbook](../studio/TESTING.md) and run the repository
local provisioner for an existing local stack. Do not reset an existing stack
just to run this example. The ignored `sdks/python/examples/base/.env` provides
the Studio export settings for local iteration.

From this directory:

```bash
uv sync --frozen
uv run junjo-coding-agents \
  --env-file ../../sdks/python/examples/base/.env \
  --spans-file runtime-data/spans.jsonl
```

Without Studio, omit `--env-file` and use `--spans-file` for local evidence.
The bridge listens on loopback port 26156. Its MCP endpoint is `/mcp`; host
OTLP/HTTP **JSON** endpoints are `/v1/traces` and `/v1/logs`. Studio export uses
the SDK's normal authenticated OTLP exporter.

Install the repository's development marketplace and plugin in another shell:

```bash
codex plugin marketplace add "$PWD"
codex plugin add junjo-coding-agents@junjo-coding-agents-dev
```

If already installed through the personal marketplace, use that installation
instead; do not enable duplicate copies. Restart the host session after plugin
installation. Changing the bridge port also requires updating `.mcp.json` and
reinstalling the plugin.

## Run with actual Codex request evidence

Configure host telemetry before starting Codex. The following overrides apply
to this CLI invocation; they do not change the user's global telemetry config:

```bash
codex exec \
  -c 'otel.exporter={otlp-http={endpoint="http://127.0.0.1:26156/v1/logs",protocol="json"}}' \
  -c 'otel.trace_exporter={otlp-http={endpoint="http://127.0.0.1:26156/v1/traces",protocol="json"}}' \
  'Use the Junjo function-review skill with diagnostic capture enabled. Spawn two native subagents for the buggy and correct fixtures. Follow the MCP step loop, print each complete_step response unchanged, and finish the execution. Return execution ID and trace ID. Stop and report any workflow error.'
```

Use the host's existing authentication and a model supported by its CLI version.
The initial live proof uses Codex 0.144.3. Its stock default model worked, while
the newer model configured for the desktop app required a newer CLI. If needed,
pass the host's normal `--model` option. Do not use `--ignore-user-config` for this
plugin proof: the tested CLI then omitted the installed plugin.

For execution without capture, request `capture=false` and omit the telemetry
overrides. If host telemetry is enabled anyway, the bridge ignores results from
uncaptured executions and exports no Junjo spans for them.

For desktop Codex, the plugin supplies the workflow tools, but model capture
also requires a host that exports the same validated telemetry. Installing a
plugin alone cannot instrument an already-running desktop session. Desktop
telemetry configuration, Cursor, and Antigravity are not validated here.

## Verify the proof

Wait for the CLI process to exit so its telemetry exporter shuts down. Then,
using the returned execution ID:

```bash
curl -fsS -X POST http://127.0.0.1:26156/flush
curl -fsS http://127.0.0.1:26156/evidence/EXECUTION_ID > runtime-data/evidence.json
uv run python scripts/validate_evidence.py \
  --evidence-file runtime-data/evidence.json \
  --spans-file runtime-data/spans.jsonl
```

This fails unless two separate native worker sessions produce four accepted
steps with attributable model spans, both branches, and the expected parentage.
Open the returned trace in Studio's full trace view under service
`junjo-coding-agents`. Inspect its Workflow graph and Store evidence as well as
the model span's source link, timestamps, model name, and host session ID.
`/flush` flushes the bridge only; it cannot force another process's host export.

Run component checks with:

```bash
uv run ruff check .
uv run ruff format --check .
uv run ty check
uv run pytest -q
uv build
```

## What the first adapter proves

An accepted step returns a random receipt. The matching successful Codex tool
result includes that receipt, the work request ID, and its source span context.
The adapter follows source ancestry to the generating sampling request and
projects its actual websocket transport span under the waiting Node. It
preserves source times and an OTel link to the original trace/span IDs. It
does not infer durations from MCP wall time or ask the assistant to estimate
tokens. These source operation names are an observed host integration surface,
not a promised stable Codex API.

Coverage is **the model request that submits each accepted step**. Complete
coverage of intermediate requests, unsubmitted failures, full prompts and
responses, per-request tokens, and other transports remains unproven. Unknown
or missing source operations produce missing evidence. Because Codex streams
tool calls, a source request may end after the corresponding Node ends; source
times are preserved rather than clipped.

The bridge receives host telemetry for the configured session. It discards
unrelated log payloads and retains compact span ancestry for correlation. Only
attributable model projections and opted-in Junjo executions are exported to
Studio. Inputs and accepted outputs are intentionally visible in native Store
evidence. Raw host transcripts and credentials must stay out of source control.

Execution state and compact source metadata live until the bridge exits. Stop
the bridge after a diagnostic session to release them. Shutdown cancels active
workflows and closes spans. This is a trusted local development process with
no persistence, durable resume, remote authentication, or public deployment.

## Ownership

- `src/junjo_coding_agents/workflow.py`: real example graph and state.
- `runtime.py`: typed handoff and execution lifecycle.
- `codex_telemetry.py`: host-specific evidence correlation and OTel projection.
- `server.py`: MCP, loopback receiver, exporter ownership.
- `plugins/junjo-coding-agents`: installable manifest, MCP connection, skill.
- `.agents/plugins/marketplace.json`: repository development installation.
- `tests`: provider-free regression checks; `scripts`: live artifact verification.

See [ADR 0017](../../docs/adr/0017-coding-agent-workflow-proof.md). Studio,
the Python SDK, and the shared telemetry contract are not modified by this proof.

# Junjo + OpenAI Agents SDK

This example proves the additive integration installed by:

```bash
uv add "junjo[openai-agents]"
```

The outer OpenAI Agent calls a native Junjo Workflow and a native Junjo Agent
as function tools. All three runtimes emit into one application-owned
OpenTelemetry provider and appear in one Junjo AI Studio trace. The same
application declarations expose external-Agent, native-Workflow, and
native-Agent targets to Junjo's Studio-controlled evaluation runner.

The example names the outer OpenAI workflow `Authentic local place
recommendation` and its nested reviewer task `Local place realism review`, so
Studio presents domain operations instead of the SDK's generic `Agent workflow`
default.

The checked-in model is deterministic and offline. This keeps normal runs,
tests, and evaluation plumbing reproducible without an API key. Replace the
`ScriptedModel` in `application.py` with any OpenAI Agents SDK model when
adapting the example to a real application. Its model spans explicitly carry
the fixture marker that Studio renders with a `Fixture` chip and code icon;
ordinary provider-backed spans do not.

## Run the application

```bash
cp .env.example .env
uv run --env-file .env junjo-openai-agents-example
```

Set `JUNJO_AI_STUDIO_API_KEY` to send the mixed trace to the local Studio.
`JUNJO_AI_STUDIO_OTLP_ENDPOINT` remains the ordinary OTLP host-and-port value;
transport security is selected independently with
`JUNJO_AI_STUDIO_OTLP_INSECURE`.

## Run the HTTP application

The FastAPI entrypoint demonstrates the same execution beneath a real inbound
application request:

```bash
uv run --env-file .env uvicorn base_openai_agents.web:app \
  --host 127.0.0.1 --port 8000
```

From another terminal:

```bash
curl -X POST http://127.0.0.1:8000/recommendations \
  -H 'Content-Type: application/json' \
  -d '{"message":"Recommend a realistic local place for a weekend afternoon."}'
```

Standard OpenTelemetry FastAPI instrumentation emits the HTTP `SERVER` span.
The OpenAI workflow and every nested OpenAI and Junjo operation remain in the
same trace beneath that request. The `/healthz` endpoint is excluded from
tracing so readiness traffic does not add noise.

## Inspect and run evaluations

Create a Studio access token, set `JUNJO_AI_STUDIO_CLI_TOKEN`, then let a coding
agent use the installed Junjo evaluation skill:

```bash
uv run --env-file .env junjo eval skill path
uv run --env-file .env junjo eval skill path --name junjo-openai-agents
uv run --env-file .env junjo eval capabilities
uv run --env-file .env junjo eval targets list
uv run --env-file .env junjo eval evaluators list
```

A developer can then ask their coding agent:

> Build a small evaluation dataset that checks the scripted response for an
> expected locality marker, run a baseline, and summarize the failures with
> links to the exact spans.

The installed skill owns target discovery, dataset construction, execution,
and evidence querying. The developer does not need to manually construct REST
requests or copy telemetry into Studio.

This example's `contains_text` evaluator is deliberately small and
deterministic. It proves that an explicit expected string can pass (for
example, `{"text": "Brooklyn"}` against the scripted Brooklyn response) and
that an absent string can fail (for example, `{"text": "Queens"}`). This is a
contract and locality-marker check for the evaluation plumbing; it does not
prove that a recommendation is factually real, current, or high quality. A
real application should use a separately calibrated domain evaluator for that
claim.

## Privacy

OpenAI Agents SDK `RunConfig.trace_include_sensitive_data` owns source-content
capture. Its upstream default is enabled, which makes this example's prompts,
responses, and tool payloads inspectable in Studio. Those spans can contain
user data or secrets; set that option to `False` when adapting the example to
a deployment that must not export the content. Junjo never serializes the
OpenAI tracing API key.

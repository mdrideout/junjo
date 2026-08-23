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

The checked-in model is deterministic and offline. This keeps normal runs,
tests, and evaluation plumbing reproducible without an API key. Replace the
`ScriptedModel` in `application.py` with any OpenAI Agents SDK model when
adapting the example to a real application.

## Run the application

```bash
cp .env.example .env
uv run --env-file .env junjo-openai-agents-example
```

Set `JUNJO_AI_STUDIO_API_KEY` to send the mixed trace to the local Studio.
`JUNJO_AI_STUDIO_OTLP_ENDPOINT` remains the ordinary OTLP host-and-port value;
transport security is selected independently with
`JUNJO_AI_STUDIO_OTLP_INSECURE`.

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

> Build a small evaluation dataset for realistic local-place responses, run a
> baseline, and summarize the failures with links to the exact spans.

The installed skill owns target discovery, dataset construction, execution,
and evidence querying. The developer does not need to manually construct REST
requests or copy telemetry into Studio.

## Privacy

The local `.env.example` enables span content capture so prompts, responses,
and tool payloads are inspectable. Those spans can contain user data or
secrets. Choose the OpenTelemetry GenAI content-capture setting deliberately
for production deployments.

---
title: "Model drivers and provider clients"
description: "Use your provider SDK or model library with Junjo Agents. Translate responses and token usage, own client lifetime, and evaluate provider changes with the same application targets."
---

A Junjo Agent calls an application-owned `ModelDriver`. Your driver uses your
chosen provider SDK or library, then translates its response into Junjo's typed
contract. Junjo owns Agent execution, tool validation, and execution evidence;
your application owns the model client, credentials, and provider-specific
translation.

Workflow Nodes can call a model client directly. The `ModelDriver` boundary is
for Junjo Agents; adding telemetry to an existing framework does not require
replacing that framework's model integration.

## Run an existing provider adapter

The [AI Chat example](https://github.com/mdrideout/junjo/tree/master/sdks/python/examples/ai_chat)
contains application-owned Gemini and Grok adapters. These are example files,
not built-in imports from the `junjo` package.

In a Junjo checkout, follow the example's environment setup. Select `gemini`
with `GEMINI_API_KEY`, or `grok` with `XAI_API_KEY`, using
`AI_CHAT_MODEL_PROVIDER` in its `.env`. The example's settings select the model
and provider timeout. Then run this from `sdks/python/examples/ai_chat/backend`:

```bash
uv sync --frozen
```

This probe sends one real request through the selected example adapter and
prints its normalized output and reported usage. It exercises the adapter
boundary; an Agent execution normally constructs this `ModelRequest` for you.

```bash
uv run --env-file ../.env python - <<'PY'
import asyncio
import json
from uuid import uuid4

from junjo.agent import AgentInputMessage, FinalOutputResponse, ModelRequest
from junjo.agent.messages import response_to_json

from ai_chat.bootstrap import build_provider_runtime
from ai_chat.config import Settings


async def main():
    runtime = build_provider_runtime(Settings.from_environment())
    try:
        driver = runtime.model.shared_driver
        assert driver is not None
        response = await driver.request(ModelRequest(
            agent_key="provider_adapter_demo",
            run_id=str(uuid4()),
            ordinal=1,
            instructions="Answer the question in the requested output format.",
            messages=[AgentInputMessage({"question": "What is a refund?"})],
            tools=[],
            output_schema={
                "type": "object",
                "properties": {"answer": {"type": "string"}},
                "required": ["answer"],
                "additionalProperties": False,
            },
        ))
        assert isinstance(response, FinalOutputResponse)
        print(json.dumps(response_to_json(response), indent=2))
    finally:
        await runtime.close()


asyncio.run(main())
PY
```

To use the same adapter in a Junjo Agent, pass `runtime.model` as the Agent's
`model` argument. The [specialist agent guide](/docs/python/agents/) shows the
typed Agent definition and `execute()` call. For Studio evidence, configure
[application telemetry](/docs/observability/opentelemetry/) around that execution.

## What the adapter translates

| Boundary | AI Chat implementation |
| --- | --- |
| Request | `provider_prompt()` serializes the normalized instructions, messages, tool declarations, and output schema from `ModelRequest.to_json()`. |
| Provider operation | `GeminiModelDriver.request()` calls Google's `generate_content`; `GrokModelDriver.request()` uses xAI's structured `chat.parse`. |
| Response | `ProviderDecision.to_junjo()` converts a validated decision into `FinalOutputResponse` or `ToolCallsResponse`, including tool-call IDs, names, arguments, and optional assistant text. |
| Usage | `_gemini_usage()` and `_grok_usage()` map reported input, output, cached-input, reasoning, and total token counts into `ModelUsage`. Unreported counts remain absent, not zero. |
| Model identity | Each binding declares a credential-free `ModelDriverDescriptor` with provider, model, adapter key, and behavior-affecting settings. |

Read the [shared decision conversion](https://github.com/mdrideout/junjo/blob/master/sdks/python/examples/ai_chat/backend/src/ai_chat/adapters/model/provider_decision.py),
[Gemini adapter](https://github.com/mdrideout/junjo/blob/master/sdks/python/examples/ai_chat/backend/src/ai_chat/adapters/model/gemini.py),
and [Grok adapter](https://github.com/mdrideout/junjo/blob/master/sdks/python/examples/ai_chat/backend/src/ai_chat/adapters/model/grok.py)
for the complete translation. The structured JSON decision envelope is this
example's choice. Your adapter can instead translate native provider tool calls
and responses into the same Junjo contract.

## Own the client lifetime

The example creates one provider client in
[`build_provider_runtime()`](https://github.com/mdrideout/junjo/blob/master/sdks/python/examples/ai_chat/backend/src/ai_chat/bootstrap.py)
and uses `ModelDriverBinding.shared()` to share its driver across Agent runs.
That declaration requires the application to ensure the driver and client are
safe for concurrent use. The application closes the client after its work has
finished; the probe makes that ownership explicit with `finally`.

Use `ModelDriverBinding.per_run()` when a driver needs isolated mutable state
for each Agent execution. Its factory is synchronous and called lazily once
per run. A per-run binding does not transfer client cleanup to Junjo; arrange
resource cleanup in your application. Keep credentials and live clients out
of the descriptor, which is recorded as evidence.

## Evaluate a provider or adapter change

Keep the same Agent target and locked dataset while changing the model binding
or adapter. Compare outcomes, duration, and the usage actually reported by the
provider; inspect execution evidence behind a regression. Model identity and
normalized responses make those implementation changes visible without making
the provider SDK part of Junjo's runtime dependencies.

Continue with [datasets and local evaluation runs](/docs/python/evaluation/),
or use [scripted driver tests](/docs/python/agents/testing/) to test request,
tool, and failure handling without making a live model call. The example's
[provider tests](https://github.com/mdrideout/junjo/blob/master/sdks/python/examples/ai_chat/backend/tests/test_provider_runtime.py)
also verify response translation and the difference between missing and
reported-zero usage.

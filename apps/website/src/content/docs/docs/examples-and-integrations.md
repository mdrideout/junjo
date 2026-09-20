---
title: Examples and integrations
description: Find runnable Junjo examples by Agent runtime, model SDK, telemetry integration, and application state pattern.
---

Start here when choosing libraries or investigating a Junjo SDK integration.
The examples own their runnable configuration and dependencies; the linked
guides explain the supported boundaries.

**Recommended starting point for native Junjo Agents with OpenAI:**
[junjo_openai_sdk](https://github.com/mdrideout/junjo/tree/master/sdks/python/examples/junjo_openai_sdk).
Its order-support Agent uses a direct Node tool and a conditional Workflow tool
on one typed application Store. Run eligible and ineligible orders, then follow
the recorded facts, policy decision, and model answer in Studio. The README
shows factory-created and caller-supplied Stores, explicit isolated mappings,
and the Agent's separate private runtime state.

| Example | Execution runtime | Provider SDK | Instrumentation | Demonstrates | Setup requirements |
| --- | --- | --- | --- | --- | --- |
| [junjo_openai_sdk](https://github.com/mdrideout/junjo/tree/master/sdks/python/examples/junjo_openai_sdk) | Junjo Agent and Workflow | OpenAI Python SDK | Junjo + OpenInference OpenAI | Direct Node and conditional Workflow tools; shared application state; both Store creation options | Python/uv, OpenAI key/model, Studio endpoint/key; mocked tests need no credentials |
| [Getting started](https://github.com/mdrideout/junjo/tree/master/sdks/python/examples/getting_started) | Junjo Workflow | None | Native Junjo; no exporter configured | Typed Store actions and conditional graph edges | Python/uv; no provider or Studio required |
| [AI Chat](https://github.com/mdrideout/junjo/tree/master/sdks/python/examples/ai_chat) | Junjo Agents and Workflows in FastAPI | Google GenAI or xAI | Junjo + OpenInference Google GenAI or xAI SDK tracing; FastAPI OTel | A complete chat application, specialist Agents, provider adapters, and evaluation targets | Provider key; Docker Compose or Python/Node; Studio credentials for evidence/evaluation |
| [base_openai_agents](https://github.com/mdrideout/junjo/tree/master/sdks/python/examples/base_openai_agents) | External OpenAI Agents SDK + nested Junjo executions | Scripted model by default | Junjo OpenAI Agents tracing bridge; FastAPI OTel | External runtime tools, mixed traces, and evaluation | Python/uv; no provider key for scripted runs; Studio credentials for evidence/evaluation |
| [Standalone evaluation](https://github.com/mdrideout/junjo/tree/master/sdks/python/examples/evaluation_standalone) | Junjo evaluation tooling and targets | None; scripted driver | Native Junjo | Independent application declarations, Studio datasets, and execution evidence | Built SDK wheel and Python environment; Studio telemetry key and developer token for runs |

Follow each example's README for its exact dependency and environment setup.
Creating a Store in a factory and sharing it with selected executions are
independent choices; see [Store composition](/docs/python/agents/composition/).

For native Junjo Agents, read [Agent definitions](/docs/python/agents/),
[Store composition](/docs/python/agents/composition/), and
[model drivers](/docs/python/agents/model-drivers/) together. Junjo runs the Agent
loop; the chosen provider SDK sends model requests. Add its instrumentor through
[OpenInference and OpenTelemetry](/docs/observability/opentelemetry/#native-model-sdks-with-openinference)
to capture provider-call evidence in Studio.

For the external OpenAI Agents SDK, read its
[dedicated integration guide](/docs/python/integrations/openai-agents/).
For deployment and credentials, start with [Studio deployment](/docs/studio/deployment/).
Configure the application and diagnostic entrypoints through the same telemetry
bootstrap, then verify one representative trace before relying on the setup.

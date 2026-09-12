# Homepage strategy notes

## Follow-up: explain Junjo's product shape earlier

Raised September 7, 2026. Deferred while the SDK building-blocks section is planned.

The earlier homepage sections need to explain tangibly what developers add:

- A Python SDK installed in and executed by their application.
- Separately deployed, containerized Junjo services that receive telemetry and
  store execution evidence, evaluation datasets, and results.
- Their application executes its targets and evaluators; their coding agent
  develops and improves it using Junjo's diagnostic and evaluation tooling.

Show where these components run and how they connect to the existing stack.
Preserve the distinction between broad OpenTelemetry integration and optional
adoption of Junjo's Python execution building blocks. Revisit placement and copy
after the current section is defined; do not modify the earlier sections yet.

## Current focus: concrete Python SDK building blocks

Lead the section with what the SDK adds to application code: specialist agents,
nodes, structured workflows, conditionally traversed graphs, RunConcurrent, and
typed workflow state with explicit store actions. Explain how capabilities can
be exposed as tools in an existing application.

Speed, responsiveness, accuracy, and observability are benefits to connect to
each building block, rather than substitutes for describing the building blocks.
Visuals should make their concrete responsibilities and composition apparent.

## Model and library freedom section

Implemented September 7, 2026: “Keep your models. Keep your libraries.”
Separate model providers, model-access libraries, and gateways/inference runtimes.
The logo chips are representative examples developers may use in their own
applications, not a popularity ranking or a list of built-in Junjo adapters.
Provider-specific calls stay in application code or application-owned model
drivers. Capturing model-call detail requires appropriate instrumentation.

Selection was checked against current primary references:

- OpenAI SDKs: https://developers.openai.com/api/docs/libraries
- Anthropic SDKs: https://platform.claude.com/docs/en/cli-sdks-libraries/overview
- Gemini SDKs: https://ai.google.dev/gemini-api/docs/libraries
- LiteLLM: https://docs.litellm.ai/docs/
- LangChain provider directory: https://docs.langchain.com/oss/python/integrations/providers/overview
- PydanticAI providers: https://pydantic.dev/docs/ai/models/overview/
- Instructor: https://python.useinstructor.com/
- OpenRouter: https://openrouter.ai/docs/quickstart
- DeepSeek: https://api-docs.deepseek.com/
- Qwen: https://www.alibabacloud.com/help/en/model-studio/compatibility-of-openai-with-dashscope
- Kimi: https://platform.kimi.ai/docs/overview
- Z.ai: https://docs.z.ai/guides/overview/quick-start
- MiniMax: https://platform.minimax.io/docs/guides/quickstart-preparation
- Ollama: https://docs.ollama.com/
- Groq: https://console.groq.com/docs/overview

OpenRouter rankings measure token traffic through OpenRouter, not total market
share across direct provider APIs and SDKs: https://openrouter.ai/rankings
Logo provenance is recorded in public/brands/models/README.md.

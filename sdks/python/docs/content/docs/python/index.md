---
title: "Junjo Python SDK: building blocks for AI applications"
description: "Add workflows, specialist agents, state management, telemetry, and local evaluations to your Python application for recursive self improvement."
---
<!-- migrated-from: sdks/python/docs/index.rst; source-hash: sha256:ec65754d16af245057495b2cd94631176509bd375a7d33ec8c3b389c6803d6da -->

[Junjo on PyPI](https://pypi.org/project/junjo/)

> 順序 (junjo): order, sequence, procedure

The Junjo Python SDK lives in your application. It gives your coding agent
building blocks, telemetry instrumentation, and evaluation tools for
[recursive self improvement](/docs/recursive-self-improvement/): investigating
failures, changing the implementation, and measuring the result.

[Junjo AI Studio](/docs/studio/overview/) is the separately deployed telemetry
and evaluation observation service. It stores datasets, evaluation outcomes,
and execution history so your coding agent and your team can inspect the same
evidence. Your application executes the code, model calls, and evaluators.

Use a Workflow when the application knows the possible procedure in advance,
and an Agent when a model must choose among an explicit set of typed Tools at
runtime. Both execution modes remain isolated, testable, and observable.

## Benefits

- ✨ Visualize your AI workflows
- 🧭 Inspect dynamic Agent model and Tool operation timelines
- 🧠 Redux inspired state management and state debugging tools
- ⚡️ Concurrency and type safety native with asyncio and pydantic
- 🔗 Organize conditional chains of LLM calls into observable graph workflows
- 🏎️ Easy patterns for directed graph loops, branching, and concurrency
- 🧪 Repeatable improvement experiments
    - Ask your coding agent to create targeted datasets from observed failures or synthetic scenarios
    - Execute Node, Workflow, and Agent targets locally against locked cases
    - Compare pass/fail results, operational errors, and execution evidence in Studio
    - Keep pytest for local correctness tests alongside the shared evaluation lifecycle
- 🔭 OpenTelemetry native
    - Provides organized, structured traces to any OpenTelemetry provider
    - [Junjo AI Studio](/docs/studio/overview/) makes received traces and evaluation evidence queryable by coding agents and inspectable by humans

## Junjo's Philosophy

**🔍 Transparency**

Ground improvements in observed behavior. Execution chronology helps your
coding agent locate a failing operation; evaluation datasets help establish
whether a proposed change improves the tested cases. Available detail depends
on the instrumentation and content capture your application configures.

**⛓️‍💥 Decoupled**

Junjo doesn't change how you implement LLM providers or make calls to their services.

Continue using [google-genai](https://github.com/googleapis/python-genai), [openai-python](https://github.com/openai/openai-python), [grok / xai sdk](https://github.com/xai-org/xai-sdk-python), [anthropic-sdk-python](https://github.com/anthropics/anthropic-sdk-python), [LiteLLM](https://github.com/BerriAI/litellm) or even REST API requests to any provider.

Model calls inside Workflow Nodes use your chosen clients directly. Native
Junjo Agents use an application-owned `ModelDriver` to translate between that
client and Junjo's typed request/response contract. Credentials and provider
configuration stay in your application.

Junjo helps organize Python functions—whether they perform logic, model calls,
retrieval, or application I/O—into predictable, testable, and observable
Workflow and Agent executions.

**🥧 Conventional**

Junjo provides primitive building blocks for explicit graph Workflows, from
linear chains of LLM calls to conditional loops, branching paths, and
concurrent subflows. A Workflow declares its possible graph paths before
execution; model calls inside Nodes may update state used by edge conditions,
but they do not dynamically create or rewrite the graph.

The first-class `Agent` execution model handles the complementary case where
a model chooses the next capability at runtime from an explicit ordered set of
typed Tools. Agent is a sibling to `Workflow`: it does not fabricate a Graph,
share mutable run state, or delegate Junjo's limits and lifecycle to a model
provider.

Workflows use explicit Python Graph primitives and Agents use typed definitions,
bindings, and Tools. Pydantic owns the declared data boundaries.

State is modeled after the conventional [Elm Architecture](https://guide.elm-lang.org/architecture/), and inspired by [Redux](https://redux.js.org/) for clean separation of concerns, concurrency safety, and debuggability.

This helps language servers and coding agents understand large Junjo
applications without learning proprietary, hidden execution patterns.

Junjo organizes conventional OpenTelemetry spans into understandable execution
evidence. Existing OpenTelemetry providers continue to work, while [Junjo AI
Studio](https://github.com/mdrideout/junjo/tree/master/apps/studio) adds
specialized Workflow graphs, Agent timelines, Store reconstruction, and
evidence-integrity diagnostics.

**🤝 Compatible**

Junjo can work alongside external AI Agent frameworks. Application code can
expose a Junjo Workflow to one of those frameworks as a **tool** for a
high-accuracy, repeatable process such as RAG retrieval or complex document
parsing. That adapter does not turn the Workflow itself into an Agent.

You can execute autonomous agent capabilities from other libraries inside a Junjo AI workflow. For example, a Junjo workflow node can run a [smolagents](https://github.com/huggingface/smolagents) tool calling agent as a single step within a greater Junjo workflow or subflow.

Junjo's first-party [OpenAI Agents SDK integration](/docs/python/integrations/openai-agents/)
lets an OpenAI Agent invoke native Junjo Workflows and Agents as tools while
both runtimes emit one mixed OpenTelemetry trace and remain available to the
same Studio-connected evaluation loop.

## Getting Started

See the [Getting Started](/docs/python/get-started/) page for installation and basic usage.

## API Reference

See the [Api](/docs/python/api/) page for the full API reference.

<a id="eval-driven-development"></a>
## Recursive self improvement

Start with the [recursive self improvement guide](/docs/recursive-self-improvement/)
for the end-to-end development cycle. Use [evaluation datasets and runs](/docs/python/evaluation/)
for the exact SDK and CLI lifecycle, and [eval-driven development](/docs/python/testing/eval-driven-development/)
for designing useful checks and local tests.

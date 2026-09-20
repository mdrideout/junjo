# Add Junjo to this application

Help me add Junjo to this application so we can use execution evidence to diagnose failures and evaluate improvements. Adapt the approach to our existing stack and development workflow.

## 1. Read the instructions and inspect our application

Read our repository instructions and these Junjo references before proposing changes:

- Studio deployment and minimal build: https://junjo.ai/docs/studio/deployment/
- Getting started: https://junjo.ai/docs/
- Examples and integrations: https://junjo.ai/docs/examples-and-integrations/
- OpenTelemetry and native provider SDK instrumentation: https://junjo.ai/docs/observability/opentelemetry/
- If using native Junjo Agents, read all three: https://junjo.ai/docs/python/agents/, https://junjo.ai/docs/python/agents/composition/, and https://junjo.ai/docs/python/agents/model-drivers/
- If using the external OpenAI Agents SDK: https://junjo.ai/docs/python/integrations/openai-agents/
- Python evaluation tooling and coding-agent skills, if applicable: https://junjo.ai/docs/python/evaluation/

Understand how our application is built and run, what telemetry it already produces, and which Junjo integrations apply. Read the selected example README, configuration, and initialization before writing integration code. Identify the Agent runtime, provider SDK, instrumentor, and Studio exporter separately. Choose explicitly where application Stores are created or shared and how inputs, tool results, and final outputs are mapped. Reuse the same initialization path for the application and diagnostic probes.

## 2. Create a project-specific implementation plan

Propose the smallest practical integration that preserves our existing architecture. If we use Docker Compose, explain how Junjo's minimal build would fit into it. Otherwise, recommend an appropriate setup based on what you find.

Base implementation details on the relevant Junjo documentation. Identify the changes needed, any prerequisites, and how we will verify the setup. Ask about material decisions you cannot resolve from the project.

## 3. Plan the telemetry

Identify which application operations we need to observe to understand a real execution from input to outcome. Plan how to capture useful intermediate results and failures, building on existing instrumentation and respecting our data-handling requirements.

Explain how we will verify that the execution chronology is available in Junjo and accessible to our coding agent. Include relevant Junjo skills and tooling where supported, and call out any gaps.

## 4. Prepare the first runtime analysis

Choose a representative application scenario and describe how to run it in our environment, inspect its evidence, and identify opportunities for improvement.

Where evaluation tooling fits, propose a targeted dataset and evaluation criteria so future changes can be compared against a baseline. Our application runs the work; Junjo records the evidence and outcomes.

Start by presenting your findings and an actionable plan for setup, instrumentation, and the first analysis. Ground the plan in this project and the documentation, and distinguish what you verified from what still needs investigation.

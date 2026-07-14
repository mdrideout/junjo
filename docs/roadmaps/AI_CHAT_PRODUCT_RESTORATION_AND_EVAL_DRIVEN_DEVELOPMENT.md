# AI Chat Product Restoration And Eval-Driven Development Plan

- Status: Planned
- Date: 2026-07-14
- Owners: Junjo platform
- Functional baseline: commit `255f69d`

## Purpose

Restore `sdks/python/examples/ai_chat` as the real AI-powered application it
was designed to be, then adopt the new Junjo Agent, Turn, telemetry, Studio,
and persistence capabilities without replacing the product experience.

AI Chat is not a deterministic Agent test harness. It is Junjo's realistic
application and eval-driven-development proving ground. Its primary purpose is
to demonstrate how structured Workflows, model-powered Nodes, bounded Agent
autonomy, application persistence, telemetry, and live evaluations work
together in an application whose quality is probabilistic.

This plan supersedes completion claims for AI Chat product restoration in:

- [Agent Layer Strategy And Roadmap](AGENT_LAYER_ROADMAP.md)
- [Agent Horizons 1 And 2 Corrective Integration Plan](AGENT_HORIZONS_1_2_CORRECTIVE_INTEGRATION.md)
- [AI Chat Turn Persistence And Studio Diagnostics Plan](AI_CHAT_TURN_PERSISTENCE_AND_DIAGNOSTICS.md)

The Agent kernel, telemetry contract version 2, cohesive Studio trace evidence,
Turn identity, versioned persistence, execution correlation, Studio resolution,
and Compose work remain valid foundations. They do not constitute restoration
of the AI Chat product by themselves.

## Product intent

AI Chat demonstrates a real-world AI development loop:

1. an application developer expresses a known procedure as a Junjo Workflow;
2. individual Nodes use live models for bounded probabilistic work;
3. an Agent handles the open-ended portion of the experience through explicit
   application Tools;
4. Junjo records complete execution and state evidence;
5. application-owned eval cases and judges measure output quality;
6. the developer inspects failed executions in Junjo AI Studio;
7. prompts, schemas, models, Graphs, Tools, or Agent instructions are revised;
8. the eval dataset is rerun to measure the effect.

Tests prove Junjo's deterministic machinery. Evals determine whether AI Chat
behaves well.

## Baseline and correction

Commit `255f69d` is the last intact pre-Horizon AI Chat product and is the
functional, visual, and eval-development baseline. Commit `0e1999a` replaced
that application with a smaller Agent demonstration. Subsequent corrective
work restored much of the presentation and introduced valuable platform
capabilities, but it did not restore the original AI behavior.

The following reduced behavior is not an acceptable product replacement:

- a deterministic `DemoModelDriver` as the default application provider;
- generated SVGs standing in for live image generation;
- hash-selected names, locations, personalities, biographies, and avatars;
- keyword-based message classification;
- fixed work, date, general, or image-response prose;
- a seeded framework-demo conversation as the central experience;
- application tests that duplicate Agent runtime and telemetry contract tests;
- restoration tests that assert the replacement's fixed strings or span names.

The historical implementation is an acceptance oracle, not a requirement to
restore its SQL schema, module paths, or every incidental implementation
choice. The restored behavior should use the current architecture where that
architecture preserves or improves the product.

## Architectural decisions

### Retain Junjo's new foundations

Retain:

- the public Agent, Tool, ModelDriver, result, failure, cancellation, and limit
  contracts;
- server-owned, schema-versioned Turn identity and lifecycle;
- versioned JSON application objects and durable execution references;
- Workflow, Agent, Tool, Store, and nested-execution telemetry;
- application execution correlation;
- cohesive Studio `TraceEvidence` and runtime identity resolution;
- the optional per-Turn diagnostics layer and Studio deep links;
- explicit provider selection with no fallback chain;
- Compose portability and frontend/backend hot reload;
- clear domain, application, adapter, API, and frontend responsibility
  boundaries.

### Restore the application rather than simulate it

Runtime behavior uses an explicitly selected live provider. Gemini is the
historical baseline; Grok remains a supported explicit alternative where its
capabilities are equivalent. Missing credentials fail clearly.

Scripted drivers remain SDK testing tools. They may support a narrowly scoped
application infrastructure check, but they do not define the product, its
prompts, its behavior, or its primary acceptance criteria.

The application does not silently downgrade to deterministic prose or SVG
artifacts.

### Keep mandatory work in Workflows

Information required on every chat Turn is loaded by explicit Workflow Nodes.
Known specialized procedures remain visible Graph paths. A model call inside a
Node is probabilistic work inside deterministic control flow; deterministic
control flow does not mean hard-coded output.

### Use the Agent at the open-ended boundary

The general-response path is the primary Workflow-to-Agent proof. The Agent
receives the contact profile and bounded recent context prepared by the
Workflow. Optional capabilities, such as searching older history or creating
an image, are Tools.

The image Tool invokes the same structured image Workflow used by the known
image branch. It does not create a duplicate procedure.

### Keep application model capabilities narrow

The application owns narrow ports for the model operations its Workflow Nodes
require:

- text generation;
- structured generation;
- image generation;
- image editing.

Provider adapters implement those capabilities. Agent `ModelDriver` bindings
remain separate because translating an Agent operation loop is a different
responsibility from making one bounded application model call.

Do not turn Junjo into a general provider SDK.

## Target product topology

### Contact creation

```text
Create Contact Workflow
  -> concurrently establish:
       sex
       age
       personality traits
       geographic coordinates and city/state
  -> generate biography with a live model
  -> generate a context-appropriate name with a live model
  -> Avatar Subflow
       -> generate a photography concept with a live model
       -> generate a realistic avatar with an image model
  -> persist versioned Contact + Conversation objects
```

The restored Contact includes the complete useful product state from the
baseline: personality dimensions, coordinates, city/state, age, sex, name,
biography, personal history, employment, interests, family context, and the
generated avatar.

### Message handling

```text
Application durably admits a server-owned Turn
  -> Handle Message Workflow
       -> concurrently load contact and bounded recent history
       -> classify the response directive with a live model
       -> branch:
            work -> profile/history-conditioned model response
            date -> profile/history-conditioned model response
            image -> Image Response Subflow
                     -> model creates image inspiration
                     -> image model edits/generates from the contact avatar
                     -> persist generated text and image
            general -> persona-aware Junjo Agent
                       -> optional older-history Tool
                       -> optional image Workflow Tool
       -> persist response
  -> reconcile Turn status and execution references
```

The generated contact remains the speaker. Responses use the complete contact
profile and conversation history to maintain a developing personal narrative.

### Frontend behavior

Restore the original application behavior, not only its component names:

- routed conversation selection;
- multiple generated contacts and conversations;
- background conversation and message refresh;
- persisted unread state;
- correct last-message ordering;
- profile and avatar presentation;
- generated text and image bubbles;
- fullscreen image viewing;
- original styling, layout, loading behavior, and interaction model.

The debug interface is an optional layer on each persisted Turn. When disabled,
it does not alter the product surface. When enabled, it resolves persisted
Workflow, Agent, and trace identities through Studio without exposing Studio
credentials to the browser.

## Eval-driven development

### Ownership

AI Chat owns its datasets, rubrics, judge prompts, judge schemas, thresholds,
and promotion decisions. Junjo owns faithful executable execution, state
transitions, identities, and telemetry. Studio owns evidence exploration and,
in later work, experiment comparison and evaluation result querying.

The eval surface remains colocated with the capability being improved. A
recommended structure is:

```text
create_bio/
  node.py
  prompt.py
  evals/
    cases.py
    judge.py
    rubric.py
    test_eval.py
```

Pytest remains the runner. Live evals use an explicit marker and command so
they are deliberate, credentialed experiments rather than ordinary hermetic
unit tests.

### Evaluation loop

Each eval case:

1. constructs only the real input state needed by the capability;
2. executes the real Node, Workflow, or Agent with the selected live provider;
3. reads the resulting state or typed output;
4. applies deterministic assertions only to genuinely deterministic
   requirements;
5. applies a model judge to qualitative requirements;
6. records the result, reason, dataset case, prompt/artifact version, provider,
   model, latency, usage, run identity, and trace identity;
7. links failures to their exact Studio evidence.

Restore the historical biography and directive datasets first. Treat them as
the initial development evidence, not frozen golden truth. For example, the
historical biography judge required recent vacations while the generator
prompt did not; the restored eval loop should expose and resolve inconsistencies
like this through normal iteration.

### Initial eval suites

Start with the smallest suites that cover the application's important
probabilistic decisions:

- biography realism, completeness, internal consistency, and trait grounding;
- directive classification, including ambiguous and context-dependent cases;
- coherence across generated name, profile, personality, location, and avatar;
- general-response quality, persona consistency, and conversation continuity;
- work-narrative continuity and non-repetition;
- specific and geographically appropriate date suggestions;
- image relevance, visual continuity, and accompanying response quality;
- Agent Tool selection, unnecessary Tool avoidance, grounding, and final
  response quality.

Node evals make prompt iteration fast. Workflow and conversational evals prove
that individually acceptable Nodes create a coherent product together.

### Minimal Junjo eval execution surface

The historical examples call `Node.service()` directly. That is convenient but
bypasses parts of Junjo's supported execution lifecycle and telemetry. Propose
a small public eval helper through an ADR before implementation.

Conceptually:

```python
result = await evaluate_node(
    node=CreateBioNode(...),
    store=store,
    correlation=correlation,
)
```

The helper should only:

- execute a real Node through Junjo's normal lifecycle;
- preserve normal Store transitions and isolation;
- emit production-equivalent Node and Store telemetry;
- return detached resulting state and execution identity.

It does not own cases, judges, rubrics, reports, datasets, or promotion policy.
Workflow and Agent evals continue to use their existing public `execute()`
methods.

## Deterministic validation boundary

Junjo SDK tests under `sdks/python/tests` remain deterministic and comprehensive
for runtime behavior, including Agent loops, Tool validation, limits, failure,
cancellation, concurrency, composition, telemetry, and contract conformance.

AI Chat keeps only the conventional checks required to protect deterministic
application machinery:

- application and Compose startup;
- versioned-object persistence and reload;
- server-owned Turn admission and lifecycle invariants;
- API/frontend integration at the transport boundary;
- frontend build and a small number of critical interaction checks;
- debug configuration safety and persisted execution references.

Do not duplicate Junjo runtime test matrices inside AI Chat. Do not mock the
model to claim that AI product behavior has been validated.

## Work packages

### 1. Correct repository truth

- Mark the reduced AI Chat restoration incomplete.
- Make this document the product-restoration source of truth.
- Separate completed Horizon 1 kernel/evidence work from incomplete Horizon 2
  application proof.
- Remove documentation that describes deterministic demo behavior as the
  restored product.

### 2. Remove replacement behavior

- Remove the demo provider from the normal application composition path.
- Remove SVG image generation and the seeded demo character from the product.
- Remove deterministic contact synthesis, keyword classification, and fixed
  response templates.
- Remove or relocate AI Chat tests that duplicate SDK runtime tests.
- Remove acceptance tests that validate the replacement instead of the
  historical product.

### 3. Restore live provider capabilities

- Port the historical prompts and typed response schemas into the current
  responsibility boundaries.
- Implement narrow live text, structured, image-generation, and image-editing
  adapters for the supported providers.
- Restore provider and HTTP OpenTelemetry instrumentation.
- Preserve explicit provider selection and fail-fast credential handling.

### 4. Restore the contact product

- Restore the complete Contact domain object.
- Restore the original concurrent Workflow and generative Node boundaries.
- Restore the avatar-inspiration and image-generation Subflow.
- Persist Contact and Conversation as versioned application objects.
- Restore the frontend contact, profile, avatar, and conversation behavior.

### 5. Restore message handling and add the Agent cleanly

- Restore live directive classification.
- Restore profile/history-conditioned work, date, general, and image behavior.
- Use the Agent only at the open-ended general-response boundary.
- Pass mandatory contact and recent context into the Agent.
- Keep broader history search and image creation as optional Tools.
- Persist generated output and exact Workflow/Agent references on the Turn.

### 6. Restore eval-driven development

- Restore the historical biography and directive eval cases.
- Move live evals into clearly named colocated `evals` surfaces.
- Add the smallest workflow, image, persona, and Agent eval datasets needed to
  measure the complete application.
- Record exact execution identity and evidence links with each result.
- Update Junjo's eval-driven-development documentation around the real app.

### 7. Prove the evidence loop

- Run AI Chat with a live provider and Studio.
- Exercise contact creation and every message branch.
- Confirm FastAPI, model, Workflow, Node, Agent, Tool, Store, image, and
  persistence evidence share truthful trace relationships.
- Run the eval suites and follow failures into Studio.
- Confirm the optional browser debug layer resolves the same persisted runs.

## Validation and completion criteria

Product restoration is complete only when:

- a new contact is generated by real text and image models with a coherent,
  complete profile;
- general, work, date, and image conversations are generated from the contact
  profile and conversation history rather than fixed templates;
- image responses maintain visual continuity with the generated contact;
- the general branch demonstrates Workflow-to-Agent composition;
- the Agent can invoke the structured image Workflow without duplicating it;
- the original frontend behavior and styling are restored with diagnostics as
  an optional overlay;
- Turn state and execution references survive application restart;
- complete application, provider, Workflow, Agent, Tool, Store, and persistence
  evidence is inspectable in Studio;
- the restored live eval suites execute real application code and providers;
- evaluation failures identify the exact application execution in Studio;
- deterministic SDK, application-infrastructure, frontend-build, shared
  contract, and Studio validations pass in their proper ownership boundaries.

Passing scripted-driver tests, fixed-string assertions, or a credential-free
demo does not satisfy these criteria.

## Explicit non-goals

- restoring the historical SQLAlchemy schema solely for fidelity;
- making AI Chat a general-purpose Agent framework test application;
- placing probabilistic product behavior behind deterministic fallbacks;
- rebuilding provider SDKs inside Junjo;
- requiring live evals on unrelated SDK or Studio changes;
- multi-agent chat, MCP, generated interfaces, or autonomous source changes;
- building the complete Studio experiment-management plane before the local
  eval-and-evidence loop is proven.

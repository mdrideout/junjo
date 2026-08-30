# Junjo Multi-Agent Kanban Validation Application Demo

- Status: Proposed validation plan; depends on the Evidence-Backed Kanban MVP
- Date: 2026-08-29
- Owners: Junjo platform, Junjo Python SDK, and Junjo AI Studio
- Primary product strategy:
  [Junjo Evidence-Backed Kanban And Agent Work Coordination Strategy](AGENT_LAYER_EVIDENCE_BACKED_KANBAN_STRATEGY.md)
- Evaluation execution boundary:
  [ADR 0013: SDK-orchestrated, application-executed Studio evaluations](../adr/0013-application-executed-studio-evaluations.md)
- Evaluation telemetry boundary:
  [ADR 0014: Bounded evaluation telemetry context](../adr/0014-evaluation-telemetry-context.md)

## Document Role

This document owns the plan for an on-demand validation application that
demonstrates Junjo's evidence-backed Kanban coordination with real coding
agents. It defines the sample application, Board topology, worker arrangement,
execution sequence, evidence requirements, validation layers, and success
criteria.

The primary Kanban strategy owns the product semantics for Projects, Boards,
Work Items, claims, Updates, audit history, worktree-local context, cloning,
and evidence references. This document consumes those semantics and does not
redefine them.

This is a validation plan, not an implementation claim. The application and
multi-agent demonstration should be built after the Kanban MVP contracts are
accepted and implemented.

## Demonstration Goal

The demonstration should prove this product promise:

> A coding harness can adopt Junjo's distributed coding-agent guidance and
> CLI, coordinate parallel work, execute application-local evaluations, and
> preserve the resulting evidence in Junjo AI Studio without depending on
> Junjo repository internals.

The demonstration is intentionally more substantial than an API smoke test.
It should let a developer observe:

- one coding orchestrator dividing application work among parallel workers;
- multiple worktrees sharing one Board and claiming different Work Items;
- a separate worker implementing an independent approach on a cloned Board;
- concise progress, findings, decisions, commits, and evaluation evidence;
- Junjo Agents and Workflows executing inside the application being changed;
- evaluation Runs connected to the originating Board and Work Item Updates;
- application telemetry and evaluation telemetry in Studio; and
- the final code, coordination history, evaluation outcomes, and execution
  traces as one navigable improvement record.

The demo should be repeatable on demand from a clean local environment. It is
not intended to prove statistically meaningful coding-agent performance from
one run.

## Architectural Boundary

The external coding harness owns source-code work:

- reading the application repository;
- planning implementation;
- spawning coding workers;
- creating and managing Git worktrees;
- changing files;
- running tests;
- committing branches; and
- integrating the completed work.

Junjo owns the reusable improvement infrastructure:

- Projects, Boards, Work Items, claims, Updates, and audit history;
- Board context and Board cloning;
- Datasets and evaluation Runs;
- connections from work to commits and evidence;
- application-local evaluation support in the Python SDK and CLI; and
- Studio telemetry, querying, comparison, and human observability.

Studio does not spawn coding agents, edit source, own worktrees, merge
branches, or execute the application.

The application under development owns its actual Junjo Agent and Workflow
implementations. It uses Junjo as an ordinary installed SDK dependency.

```text
Coding harness
  ├── spawns workers and manages worktrees
  ├── changes application source
  └── invokes Junjo SDK guidance and CLI
             │
             ▼
Junjo coordination and measurement
  ├── Projects, Boards, Work Items, claims, and Updates
  ├── Datasets and evaluation Runs
  └── telemetry and execution evidence
             │
             ▼
Application under development
  ├── Junjo Agent
  └── Junjo Workflow
```

## Why The Coding Workers Are Not Junjo Agents

The worker layer should be Codex, Claude Code, Pi, DeepSeek Harness, or another
general coding harness. It should not be a special Junjo coding Agent.

Using Junjo Agents as coding workers would prove only that one bespoke Junjo
orchestrator can use the Kanban system. It would not validate that independent
coding harnesses can adopt the distributed skill, discover the CLI, coordinate
through Studio, and run evaluations from a normal application repository.

Junjo Agents still have a central role inside the sample application:

- one feature should execute a Junjo Agent;
- one feature should execute a Junjo Workflow; and
- an optional evaluation judge may itself be a Junjo Agent.

This cleanly demonstrates Junjo's intended position: a batteries-included
application, evaluation, coordination, and measurement layer that remains
independent of the coding orchestrator and model provider.

## Reference Coding Harness And Portability

Codex should be the first reference coding harness because the demonstration
can exercise a root coding agent, parallel sub-agents, and separate worktrees
directly. The scenario must remain harness-neutral.

After the reference flow works, the same committed fixture and high-level
prompt should be run with at least one other coding harness. Any Junjo-specific
procedure that must be added directly to a Codex-only prompt indicates missing
SDK, CLI, help text, or coding-agent guidance.

The worker prompts must not contain:

- raw Studio endpoint contracts;
- Studio database instructions;
- Junjo monorepo source paths;
- hand-written HTTP requests for claim or Update operations;
- copied Board, claim, Run, or cursor bookkeeping that context should retain;
  or
- vendor-specific Board behavior.

Workers should succeed using only:

- the installed Junjo SDK and CLI;
- the distributed Junjo coding-agent guidance;
- CLI help;
- their assigned application task; and
- the application repository's ordinary development instructions.

## Validation Application

The recommended application is a compact **Customer Feedback Desk**.

It is large enough to exercise frontend, backend, persistence, Junjo runtime,
tests, telemetry, and evaluations while remaining understandable during a
live demonstration.

### Committed Boilerplate

The clean baseline repository should contain:

- a small Python backend;
- a small React frontend;
- a persisted `Feedback` record with a title and message;
- working create and list behavior for Feedback;
- existing backend and frontend tests;
- normal application development instructions;
- Junjo installed as a package dependency;
- local Junjo AI Studio configuration examples;
- empty, explicit integration points for the two requested features; and
- no completed implementation of either feature.

The boilerplate should not import Junjo monorepo runtime code or require an
agent to know the Junjo repository layout. A test mode may install the locally
built SDK artifact, but the application must consume it exactly as an external
package would.

The integration points should prevent incidental merge conflicts without
introducing a plugin framework or dynamic discovery architecture. Each
vertical slice should own its feature directory and its already-designated
backend and frontend entry points.

### Work Item A: Feedback Categorization

The first requested vertical slice is feedback categorization.

Its task brief should require the completed application to:

- accept an existing Feedback record;
- execute a Junjo Workflow that assigns a useful category such as bug,
  feature request, question, or praise;
- persist and display the category;
- expose complete Junjo telemetry for the Workflow and its Nodes;
- register an application-local evaluation target; and
- include focused backend, frontend, and evaluation tests.

The assigned worker owns the feature's backend route, Workflow, persistence,
frontend panel, and tests.

### Work Item B: Response Drafting

The second requested vertical slice is response drafting.

Its task brief should require the completed application to:

- accept an existing Feedback record;
- execute a Junjo Agent that produces a concise suggested response;
- persist and display the draft;
- expose complete Junjo telemetry for the Agent execution;
- register an application-local evaluation target; and
- include focused backend, frontend, and evaluation tests.

The assigned worker owns the feature's backend route, Agent, persistence,
frontend panel, and tests.

### Why These Slices Are Appropriate

The slices share the base Feedback record but have distinct behavior and
implementation ownership. Together they demonstrate:

- clean parallel work on one application;
- one Junjo Workflow and one Junjo Agent;
- backend and frontend changes in each slice;
- application-local datasets and evaluations;
- independent commits and evidence; and
- a meaningful final integrated product.

This is preferable to another chat application because both responsibilities
are visible, independently useful, and easy to explain during a demonstration.

## Committed Scenario Instructions

The fixture should commit:

- the clean boilerplate;
- the two feature briefs;
- a short orchestration brief requiring the root coding agent to create the
  required Kanban items and use parallel workers;
- normal build, test, and local-run instructions; and
- evaluation intent for each feature.

It should not commit an expected source-code implementation or a step-by-step
solution. The coding agents should determine the implementation from the
application contracts and task briefs.

A realistic root prompt is:

> Build the two requested Customer Feedback Desk features. Use the Junjo work
> coordination guidance and CLI to create and manage the work on the specified
> Project. Use parallel workers where the tasks can be completed independently.
> Keep the Board updated with important findings, decisions, commits,
> evaluations, and completion status. Validate the integrated application and
> report the resulting Studio evidence.

The distributed Junjo guidance should own the detailed operating procedure.
The developer should not need to describe individual CLI commands, claim
semantics, cursor management, evidence-reference formats, or clone behavior in
the prompt.

## Project And Board Topology

Each demonstration starts with one Project and two related Boards:

```text
Project: Customer Feedback Desk demonstration
├── Board: Parallel implementation
│   ├── Feedback categorization → Worker A
│   └── Response drafting → Worker B
│
└── Board: Independent solo implementation
    ├── Feedback categorization → Worker C
    └── Response drafting → Worker C
```

The Project description explains that both Boards implement the same feature
briefs so their coordination histories and outcomes can be compared.

The shared Board description explains that its items belong to one integrated
parallel strategy. The cloned Board description explains that one worker is
independently implementing both features as a deliberately separate strategy.

### Clone Timing

For the primary deterministic demonstration:

1. Create the Project.
2. Create the parallel Board.
3. Add both TODO Work Items in their desired relative order.
4. Clone the Board before either shared worker claims an item.
5. Rename and describe the clone as the independent solo implementation.
6. Bind each worktree to its intended Board.

Cloning before claims keeps the main scenario reproducible. The DOING-to-TODO
clone mapping and claim clearing should be covered by deterministic contract
tests rather than by introducing a timing dependency into the live demo.

## Multi-Agent Execution

The full live scenario uses one root coding orchestrator and three workers.

### Root Orchestrator

The root coding agent:

1. reads the repository instructions and Junjo coding-agent guidance;
2. verifies the local application and Studio prerequisites;
3. creates or selects the demonstration Project;
4. creates the parallel Board and its two Work Items;
5. clones the Board for the independent strategy;
6. creates three isolated Git worktrees;
7. binds two worktrees to the shared Board and one to the cloned Board;
8. spawns Worker A for categorization;
9. spawns Worker B for response drafting;
10. spawns Worker C to implement both items independently;
11. monitors Board Updates rather than reconstructing worker status from chat;
12. integrates the shared workers' branches;
13. runs combined application and evaluation validation;
14. verifies the solo implementation independently;
15. reports the Board histories, commits, evaluation Runs, and execution
    evidence; and
16. leaves both Boards available for human inspection in Studio.

### Shared Workers

Worker A and Worker B each:

1. inspect their worktree-local Project and Board context;
2. read the Project and Board descriptions;
3. query recent Board Updates;
4. locate and atomically claim the assigned TODO Work Item;
5. state when another substantive update should be expected;
6. implement and test the owned vertical slice;
7. record concise findings, decisions, and important results;
8. run the relevant evaluation dataset against the application code;
9. reference its commit, evaluation Run, and execution evidence in an Update;
10. move the Work Item to DONE only after its validation succeeds; and
11. leave unrelated files and the other worker's item untouched.

The workers share one Board, so each should be able to discover the other's
claims and progress without direct chat coordination.

### Independent Worker

Worker C:

1. inspects the cloned Board context and clone lineage;
2. verifies that both cloned items are independently available;
3. claims and completes both Work Items in relative order;
4. implements its own complete approach in the third worktree;
5. records decisions, commits, evaluation Runs, and evidence on the clone;
6. never modifies the shared Board's claims or status; and
7. leaves a complete independent Board history for comparison.

The independent worker is not expected to spawn another worker. Its purpose is
to contrast a single-worker strategy with the two-worker shared strategy, not
to establish a winner.

## Evaluation And Telemetry Experience

Each feature should provide a small reusable input Dataset and a binary
evaluation contract.

The categorization Dataset should contain representative Feedback messages
with expected categories. Its evaluator records pass or fail based on the
declared expected category.

The response-drafting Dataset should contain representative Feedback messages
and explicit response expectations. A deterministic evaluator may cover
structural requirements; an optional judge may evaluate qualitative response
requirements. Studio still records each result as pass or fail rather than
inventing a required score.

Every evaluation Run should:

- execute from the application repository through the Junjo SDK harness;
- record the originating Board when started;
- keep evaluation telemetry distinct from ordinary application-use telemetry;
- retain Attempt-to-execution evidence binding;
- expose the full Agent or Workflow execution in Studio; and
- be referenced by the Work Item Update that interprets its result.

The completed shared implementation should also be exercised through the
normal application UI so the developer can observe ordinary application
telemetry alongside the separate evaluation Runs.

## What The Demonstration Validates

### Coordination

- Multiple workers can discover and use the same Board.
- Atomic claims prevent duplicate ownership of one Work Item.
- Different workers can hold different items concurrently.
- Worktree-local Board context remains correct across agent sessions.
- Workers can query changes made by other workers.
- Updates communicate substantive progress without becoming an activity log.
- Work Items move through TODO, DOING, and DONE.
- Commits and evidence remain attached to the work that produced them.

### Board Independence And Cloning

- A Board can be cloned from an exact revision.
- Board and Work Item lineage remain visible.
- Claims do not cross between the source and clone.
- Ordering, Updates, and state change independently after cloning.
- Shared workers remain on the shared Board.
- The solo worker reliably remains on the cloned Board.
- No implicit synchronization or merge occurs between Boards.

### Application Behavior

- Both vertical slices work independently and after integration.
- The Workflow and Agent execute through ordinary Junjo application code.
- Backend, frontend, persistence, and tests remain coherent.
- The application can be started and used from a clean checkout.

### Evaluation And Evidence

- Workers can discover registered targets and evaluators.
- Datasets are reusable and not owned by either Board.
- Evaluation Runs record their originating Board.
- Work Item Updates can reference the relevant Dataset, Run, Attempt,
  execution, and commit.
- Evaluation Runs are distinguishable from normal application-use Runs.
- Individual outcomes deep-link into the full Agent or Workflow execution.
- Shared and independent strategies can be inspected through their evidence
  without copying trace payloads into Kanban Updates.

### Portability

- The fixture behaves like an external application repository.
- The application depends only on the packaged Junjo SDK and documented
  public Studio contracts.
- Workers operate through the distributed guidance and CLI help.
- No direct database manipulation or Junjo-source import is required.
- The same scenario can be attempted by a second coding harness without
  changing Junjo's Board semantics.

## Validation Layers

The feature needs three separate validation layers. They should not be
collapsed into one nondeterministic agent run.

### 1. Deterministic Automated Acceptance

Normal automated tests should exercise:

- Project and Board creation;
- ordered Work Item creation and movement;
- atomic claim success and conflict behavior;
- Update creation and cursor-based Board queries;
- release, abandon, overdue visibility, and explicit reclaim;
- transactional cloning and state mapping;
- claim clearing on clones;
- Work Item lineage;
- worktree-local context isolation;
- optional Board origin on evaluation Runs; and
- bounded evidence references.

These tests validate product contracts without relying on a coding model to
produce the same implementation twice.

### 2. Real Coding-Agent E2E Demonstration

An opt-in runner should generate a fresh Git repository from the committed
boilerplate and execute the root-plus-three-workers scenario.

This validates the human experience, CLI discoverability, skill quality,
worktree behavior, Board usefulness, and evidence loop. It should not be a
required deterministic unit-test gate because coding-agent source output and
external model availability are variable.

### 3. Optional Live-Model Evaluation

The completed application may run its Workflow, Agent, and qualitative judge
against configured live model providers. This produces realistic evaluation
and telemetry evidence for a product demonstration.

The structural coordination and application validation must also support a
deterministic model substitute so external credentials are not required to
prove that the system works.

## Claim-Recovery Validation

The main coding scenario should not intentionally stall a worker merely to
demonstrate recovery. That would make the primary demo slower and less
reproducible.

Deterministic automated acceptance should validate overdue, abandon, release,
and reclaim semantics completely. An optional live control-plane rehearsal may
create a disposable Work Item, publish an intentionally expired promised
update time, and perform one explicit audited reclaim. It must remain separate
from the two feature implementations.

## Repeatability And Reset

The on-demand runner should start from explicit clean state:

1. reset the local Studio development data through the supported greenfield
   workflow;
2. provision the normal local Studio user and developer credential through
   supported application flows;
3. create a fresh repository from the committed boilerplate;
4. initialize and commit the baseline;
5. configure the application with local Studio endpoints and credentials;
6. create a new demonstration Project and Boards;
7. execute the selected coding harness; and
8. retain the finished repositories and Studio data for review.

Reset behavior must not seed records through direct database edits. The demo
should use the same public or application-owned setup flows available to a
developer.

The runner should print the repository locations, branch names, Project,
Boards, Work Items, evaluation Runs, and Studio URLs needed for inspection.

## Demonstration Report

Each run should produce a compact report containing:

- coding harness and model configuration;
- baseline repository revision;
- Project identity;
- source and cloned Board identities and lineage;
- worker, worktree, branch, and claim assignments;
- Work Item completion state;
- significant Update timeline entries;
- implementation commits;
- application test results;
- evaluation Datasets and Runs;
- passed and failed binary outcomes;
- Agent and Workflow execution links;
- integration results for the shared approach; and
- validation results for the independent approach.

The report references canonical source control and Studio records. It does not
duplicate complete diffs, datasets, prompts, conversations, or span payloads.

## Interpreting Shared And Independent Results

The two approaches may be compared for:

- completion correctness;
- elapsed orchestration time;
- duplicated effort;
- merge or integration effort;
- claim conflicts;
- usefulness and completeness of Updates;
- test results;
- evaluation outcomes; and
- trace-level execution differences.

One run does not establish that parallel or solo work is universally better.
Junjo's job is to preserve the evidence and make both approaches inspectable,
not to automatically select a winning strategy.

## Expected Repository Artifacts

The implementation should eventually provide:

1. a committed external-style Feedback Desk boilerplate;
2. the two feature briefs and root orchestration brief;
3. a deterministic fixture-reset and repository-creation command;
4. automated Kanban contract and context tests;
5. an opt-in real coding-agent demonstration runner;
6. deterministic application and evaluation fixtures;
7. optional live-model configuration; and
8. a generated demonstration report containing Studio evidence links.

The exact repository directory belongs in the implementation plan. The
fixture should live near agent-facing E2E tooling rather than becoming another
production application or an extension of AI Chat.

## Implementation Sequence

Build the demonstration incrementally after the Kanban MVP exists:

1. **Contract acceptance:** validate the Project, Board, Work Item, claim,
   Update, context, clone, and Run-origin contracts deterministically.
2. **External-style fixture:** commit the Feedback Desk baseline and prove it
   starts and passes its existing tests without either feature.
3. **Single-worker proof:** have one coding worker complete one Work Item using
   only distributed Junjo guidance and CLI help.
4. **Shared-board proof:** run the two independent vertical slices in parallel
   on one Board and integrate them.
5. **Cloned-board proof:** run the solo strategy on the cloned Board and verify
   isolation and lineage.
6. **Evidence proof:** run datasets, inspect binary outcomes, and open linked
   Agent and Workflow executions in Studio.
7. **Portability proof:** repeat the scenario with another coding harness and
   improve only the general SDK, CLI, or guidance where necessary.

Each stage should be working and reviewable before moving to the next.

## Explicit Non-Goals

This validation application does not justify:

- a Junjo-native coding agent;
- source-code execution inside Studio;
- Studio-managed Git repositories, branches, merges, or worktrees;
- a general coding-agent scheduler;
- vendor-specific Codex, Claude, Pi, or DeepSeek Board APIs;
- dynamic application plugin infrastructure;
- custom Board columns, sprint machinery, or task dependencies;
- automatic synchronization or merging between cloned Boards;
- automatic selection of a winning implementation;
- requiring live model credentials for deterministic acceptance; or
- treating one demonstration as a coding-agent performance benchmark.

## Success Definition

The demonstration succeeds when a developer can give a supported coding
harness the high-level root prompt and observe all of the following without
manual Junjo bookkeeping:

1. the orchestrator creates the intended Project, shared Board, Work Items,
   and cloned Board;
2. two workers claim different shared items and work concurrently;
3. one worker implements both items independently on the clone;
4. each worktree reliably uses its assigned Board;
5. substantive progress and coordination are visible through Board Updates;
6. both application features execute as a Junjo Workflow and Junjo Agent;
7. the workers run application-local datasets and evaluations;
8. evaluation Runs, commits, and semantic executions are attached to the
   relevant work history;
9. the shared branches integrate into a working application;
10. the cloned strategy remains independent and auditable;
11. a human can inspect both Boards, their evaluation outcomes, and their full
    execution traces in Studio; and
12. the same scenario is usable by another coding harness without adding a
    second Junjo orchestration architecture.

This gives Junjo a repeatable demonstration of its intended RSI role: coding
agents change the application locally, while Junjo supplies shared work memory,
coordination, measurement, evidence, and human observability.

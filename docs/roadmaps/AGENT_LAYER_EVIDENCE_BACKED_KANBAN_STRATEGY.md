# Junjo Evidence-Backed Kanban And Agent Work Coordination Strategy

- Status: Proposed product strategy; not implemented
- Date: 2026-08-29
- Owners: Junjo platform, Junjo Python SDK, and Junjo AI Studio
- Related strategy:
  [Junjo Agent Layer Strategy And Roadmap](AGENT_LAYER_ROADMAP.md)
- Evaluation execution boundary:
  [ADR 0013: SDK-orchestrated, application-executed Studio evaluations](../adr/0013-application-executed-studio-evaluations.md)
- Evaluation telemetry boundary:
  [ADR 0014: Bounded evaluation telemetry context](../adr/0014-evaluation-telemetry-context.md)
- Validation application demo:
  [Junjo Multi-Agent Kanban Validation Application Demo](AGENT_LAYER_KANBAN_MULTI_AGENT_VALIDATION_DEMO.md)

## Document Role

This document owns the proposed product strategy for organizing evidence-backed
improvement work across humans and multiple coding agents. It defines Projects,
Boards, Work Items, claims, Updates, audit history, worktree-local context,
Board cloning, lineage, and connections to Junjo evaluation evidence.

This is a product and planning document. It does not accept a persistence or
API design, authorize implementation, or claim that these capabilities exist.
An implementation ADR must follow after the product semantics are accepted and
before code changes begin.

The completed Horizon 3 Lean Evaluation MVP remains a historical implementation
record. This strategy builds on that evaluation foundation rather than
rewriting it.

## Product Thesis

Junjo AI Studio should provide an evidence-backed work coordination layer
between measurement and application changes:

```text
Evaluation evidence
        ↓
Distilled work items
        ↓
Relatively ordered Board
        ↓
Atomic agent claims
        ↓
Progress, findings, and decisions
        ↓
Candidate evaluation evidence
        ↓
Resolution history
```

Without a shared coordination layer, every coding harness must independently
invent how to remember failure modes, prioritize work, avoid duplicate effort,
record what was tried, associate commits and evaluations, and coordinate
parallel workers. Those mechanics are common to the Junjo improvement loop and
belong in Junjo rather than in application-specific agent glue.

Studio remains the evidence and coordination system. It does not edit source,
create worktrees, launch coding agents, merge branches, execute application
code, or deploy candidates. Codex, Claude Code, DeepSeek Harness, or another
coding orchestrator continues to own those actions inside the application
repository.

## Organization Model

The minimal hierarchy is:

```text
Project
└── Board
    └── Work Item
        ├── concise Updates
        ├── current Claim
        └── references to commits, datasets, Runs, Attempts, and evidence
```

The organizing principle is:

> Projects organize a body of work. Boards organize one shared or deliberately
> isolated strategy. Worktrees remember which Board they are using but do not
> own the Board.

Junjo describes these layers and lets developers and agents use them according
to their strategy. It does not impose a rigid rule for whether two efforts must
share a Project or Board.

## Project

A Project is a descriptive umbrella for related work.

Examples:

```text
Project: AI Chat local-place quality
├── Board: Shared product-quality work
├── Board: Strategy A — stronger neighborhood grounding
└── Board: Strategy B — retrieval-backed recommendations
```

```text
Project: Junjo release preparation
├── Board: Product coding
├── Board: Documentation
└── Board: Release validation
```

Projects provide organization and intent. They are not application runtimes,
Git repositories, teams, or authorization boundaries.

### Required Project Meaning

Every Project requires:

- a canonical ID;
- a human-readable name; and
- a description explaining the Project's purpose and boundaries.

The description should give a coding agent enough context to decide whether
new work belongs in the Project.

### Minimal Project Data

| Field | Purpose |
| --- | --- |
| `id` | Canonical Project identity |
| `name` | Required human-readable name |
| `description` | Required explanation of purpose and boundaries |
| `created_at` | Creation time |
| `updated_at` | Last material modification time |

The initial model does not require Project status, owner, team, milestones,
estimates, custom metadata, or a separately configurable workflow.

## Board

A Board represents one work strategy or collaboration boundary inside a
Project.

Its name and description explain:

- why the Board exists;
- what belongs on it;
- what does not belong on it;
- whether agents should collaborate on one shared approach; and
- when relevant, what independent approach a cloned Board is intended to
  explore.

The model does not encode Board types such as `shared`, `worktree`, or
`experiment`. Those are strategies expressed by the Board name and
description. This keeps the organization flexible without adding a taxonomy
that cannot enforce useful behavior.

### Minimal Board Data

| Field | Purpose |
| --- | --- |
| `id` | Canonical Board identity |
| `project_id` | Owning Project |
| `name` | Required human-readable name |
| `description` | Required purpose, scope, and collaboration strategy |
| `cloned_from_board_id` | Immediate source Board when cloned |
| `cloned_from_revision` | Exact source Board snapshot when cloned |
| `revision` | Optimistic concurrency and snapshot identity |
| `created_at` | Creation time |
| `updated_at` | Last material modification time |

A Board belongs to exactly one Project. A Project may contain any number of
Boards.

### Shared Board

Agents in different worktrees should normally share one Board when their work
should know about and coordinate with other work.

```text
Shared Board
├── Agent A · worktree A · claims Item 1
├── Agent B · worktree B · claims Item 2
└── Agent C · worktree C · claims Item 3
```

The agents share:

- the same TODO list;
- the same relative ordering;
- current claims;
- recent Updates;
- completed work; and
- commits, Runs, and evidence referenced by other agents.

This is the encouraged default for related work. A new worktree alone does not
justify a separate Board.

### Separate Board

A separate Board is appropriate when work is intentionally isolated:

- unrelated subjects such as marketing and product coding;
- two independent strategies for the same problem;
- two workers exploring different complete approaches;
- speculative work that should not influence a shared plan yet; or
- a branch of work whose priorities and decisions are expected to diverge.

Separate Boards may live in the same Project or different Projects. Junjo does
not impose a hard rule. The Project and Board descriptions preserve the reason
for the chosen organization.

### Join Versus Clone

The SDK, CLI, skill, and UI must make the choice explicit:

- **Join a Board** when multiple worktrees are implementing one shared plan.
  Claims coordinate work across all participants.
- **Clone a Board** when starting an independent strategy whose work and
  decisions are expected to diverge. Claims are isolated from the source
  Board.

## Worktree-Local Context

A worktree is a local execution environment, not a canonical Studio entity.
Studio must not treat a filesystem path as Board ownership or portable
identity.

The Junjo CLI should instead retain a small untracked context scoped to the
current repository worktree:

```text
Active Project: AI Chat local-place quality
Active Board: Strategy A — neighborhood grounding
Active claimed item: Improve place-specific recommendations
Last observed Board update: 184
```

Conceptual commands are:

```text
junjo work context show
junjo work context use --project <id> --board <id>
junjo work context clear
```

The exact command spelling is an implementation decision. Required behavior
is:

- context is stored outside tracked application source;
- context is distinct per Git worktree;
- explicit command arguments may override it;
- an environment override may be provided for automation;
- the active Project and Board are always inspectable; and
- a coding agent can recover its Board and latest-seen update position after a
  new agent session begins.

The coding-agent skill should require inspecting this context before creating,
claiming, moving, completing, or cloning work.

Studio may record a human-readable workspace or branch label on an active
claim. That value describes where the claimant is working. It does not make
the worktree the owner of the Board.

## Work Item

A Work Item is one concise, actionable unit of work on a Board. It is a
distilled conclusion about something worth doing, not a copy of an evaluation
failure.

Several failed cases or Runs may support one Work Item. One failure may also
become evidence for an existing Work Item rather than creating a duplicate.

### Minimal Work Item Data

| Field | Purpose |
| --- | --- |
| `id` | Canonical Work Item identity |
| `board_id` | Owning Board |
| `lineage_id` | Stable identity inherited by cloned copies |
| `cloned_from_work_item_id` | Immediate source Work Item when cloned |
| `title` | Short actionable name |
| `description` | Problem, intended outcome, and relevant context |
| `status` | `todo`, `doing`, or `done` |
| `position` | Relative ordering within its status column |
| current claim fields | Current worker and activity state |
| `revision` | Optimistic concurrency value |
| `created_at` | Creation time |
| `updated_at` | Last material modification time |

The initial Work Item does not add:

- a category;
- a priority value;
- a target identity;
- a separate acceptance-criteria schema;
- estimates;
- labels;
- dependency graphs; or
- assignment independent from the active claim.

The description can explain what success means without creating more
structured fields. Commits, evaluation results, decisions, and validation
belong in concise Updates and evidence references.

### Work Item States

The only states are:

```text
TODO → DOING → DONE
```

Normal claim behavior is:

- claiming a TODO moves it to DOING;
- releasing or abandoning unfinished work moves it back to TODO;
- completing work moves it to DONE and clears the active claim; and
- reopening DONE moves it back to TODO.

The initial system does not add Backlog, Ready, Review, Blocked, Cancelled, or
custom states. A blocked agent posts an Update explaining the blocker and
either retains or releases the claim.

### Relative Ordering

Priority is represented by relative item order within each column. There is no
separate priority field or synthetic priority score.

The Board supports:

- moving an item before or after another item;
- moving an item between TODO, DOING, and DONE;
- returning the complete current order; and
- rejecting a conflicting reorder when the expected Board revision is stale.

For the expected small Board size, a straightforward transactional integer
ordering strategy is sufficient. The initial design does not need fractional
ranks, distributed ordering, or a conflict-free replicated sequence.

## Claiming And Coordination

### Claim Identity

One active claim may exist for a Work Item. It records:

- the Work Item;
- authenticated Studio user or developer-token identity;
- coding-agent instance or session ID;
- human-readable worker label;
- optional local branch or workspace label;
- claim ID;
- claimed time;
- last activity time; and
- next expected update time.

The authenticated principal and agent instance are distinct. A free-form agent
label alone is not sufficient audit identity.

The claim ID is an operation identity, not an authentication secret. It helps
prevent one session from accidentally updating another session's claim when
both use the same developer credential.

### Atomic Claim

Claiming uses the expected Work Item revision:

1. The agent reads the Work Item and current revision.
2. The agent requests a claim using that revision.
3. Studio accepts the claim only if the item remains available and unchanged.
4. An accepted claim moves the item to DOING in the same transaction.
5. Otherwise Studio returns a conflict with the current item and claimant.

Studio does not implement a distributed worker scheduler or source-code lock.
A claim communicates and protects work ownership inside the Board; it does not
lock files, branches, Nodes, Workflows, Agents, or evaluation targets.

### Activity And Overdue Claims

The claimant declares when another update should be expected. A later Update
or explicit check-in may move that expectation.

```text
Claimed at:           10:00
Last activity:        10:18
Next update expected: 10:45
```

Studio derives the visible state:

- **active** when the next promised update is not overdue;
- **overdue** when the promised time has passed;
- **abandoned** when the claimant explicitly records abandonment; and
- **released** when the claimant deliberately makes the work available.

An overdue claim is a coordination signal. Studio never silently expires,
releases, or transfers it.

This avoids a fixed global lease duration, background heartbeat service, and
automatic task stealing while still making stalled work machine-queryable.

### Release, Abandon, And Reclaim

- **Release** clears the claim and returns unfinished work to TODO.
- **Abandon** records why the work stopped, clears the claim, and returns the
  item to TODO.
- **Reclaim** lets another authorized agent take an overdue or abandoned item
  through an explicit atomic action.

Reclaiming requires the current Work Item revision, a concise reason, the new
claimant identity, and a new expected update time. It is always present in the
audit log.

There is no separate persisted `blocked` state. A blocker is communicated in
an Update. The claimant decides whether to continue holding or release the
item.

## Work Item Updates

Work Item Updates are the concise, human- and agent-readable collaboration
history. They explain substantive progress without copying source-of-truth
artifacts.

An Update may record:

- what was investigated;
- what was tried;
- what happened;
- what was learned;
- why a decision was made;
- what remains unresolved;
- which commit implemented a change;
- which Dataset, Run, Attempt, comparison, or execution informed the work;
- whether a candidate improved or regressed behavior; and
- when the claimant expects to update the item again.

### Minimal Update Data

| Field | Purpose |
| --- | --- |
| `id` | Canonical Update identity |
| `work_item_id` | Owning Work Item |
| `body` | Concise Markdown summary |
| actor identity | User, developer token, and agent instance |
| references | Optional commits, Datasets, Runs, Attempts, comparisons, or executions |
| `next_update_at` | Optional new update expectation for the active claim |
| `created_at` | Original timestamp |

The initial model does not add Update categories, nested replies, reactions,
rich attachments, or a separate discussion system.

### Source-Of-Truth Discipline

An Update references evidence rather than reproducing it.

Good:

> Changed the date-response instructions to require neighborhood-specific
> venues. Commit `abc123`. Candidate Run `run-42` improved four cases and
> regressed one. Investigating the regression next.

Bad:

> Copy the complete prompt, response, trace, diff, and evaluation payload into
> the Update body.

Commit diffs remain in source control. Datasets and evaluation records remain
in Studio evaluation control. Complete spans remain in the telemetry evidence
plane.

## Updates Versus Audit History

Work Item Updates and audit history have separate purposes.

### Updates

Updates are deliberately authored high-level knowledge:

- findings;
- attempts;
- results;
- decisions;
- commits; and
- next steps.

This is what agents normally read to understand work performed by other
agents.

### Audit History

Audit events are automatically written immutable control records:

- Project or Board created;
- Board cloned;
- Work Item created;
- Work Item reordered;
- Work Item claimed;
- claim released, abandoned, or reclaimed;
- status changed;
- Update posted; and
- evidence reference added.

An audit event records the event type, authenticated principal, agent instance,
Board sequence, Work Item when applicable, relevant old and new control values,
and timestamp. It does not duplicate the full Update body, commit diff, or
telemetry payload.

Canonical state changes and their audit events are committed in the same
SQLite transaction. Canonical Project, Board, Work Item, and claim rows retain
the current state. The audit log does not turn this feature into an
event-sourced system.

## Board Updates Query

A Board exposes a coding-agent-friendly Updates query that answers:

> What changed on this Board since I last checked?

Conceptual CLI operations are:

```text
junjo work updates list
junjo work updates list --since <cursor>
junjo work updates list --item <id>
```

The exact commands are an implementation decision. The product response must:

- use a monotonic cursor;
- group Updates by Work Item;
- include each item's current status and relative position;
- include current claimant and activity state;
- include timestamps and references;
- identify control changes even when no authored Update accompanied them; and
- support resuming from the worktree's last-observed cursor.

An example projection is:

```text
Work item: Improve local-place specificity
Status: DOING
Claimed by: codex-strategy-a
Claim state: active
Last updated: 2026-08-29 14:32

  14:32 — Candidate Run run-42 improved four cases and regressed one.
  13:58 — Commit abc123 changed the date-response instructions.
  13:20 — Baseline evidence points to generic venue selection.
```

The response may also identify a control-only change:

```text
Work item: Reduce unnecessary search calls
Status: TODO
Latest activity: claim released at 14:10
```

The worktree-local context may remember the last observed cursor. A normal
coding-agent synchronization flow is therefore:

```text
junjo work context show
junjo work updates list --since-last-seen
junjo work items list
```

This makes work performed by other agents easy to discover without requiring
the developer to relay status manually.

## Board Cloning And Lineage

Cloning creates an independent, auditable snapshot. It does not create a live
fork or synchronization relationship.

### Clone Transaction

The clone operation takes a consistent source Board revision and creates:

- a new Board ID;
- a new Board name and description supplied for the independent strategy;
- a new Board revision history;
- new Work Item IDs;
- inherited Work Item lineage IDs;
- immediate source Work Item references;
- inherited Work Item content and relative ordering;
- inherited concise Updates available at the clone revision; and
- inherited evidence references.

The clone records the source Board ID and exact source revision. It may be
created in the same Project or a different Project.

### State Mapping

| Source state | Cloned state |
| --- | --- |
| TODO | TODO |
| DOING | TODO |
| DONE | DONE |

All claims, activity deadlines, and overdue state are cleared. Active source
work becomes available because the cloned strategy has no owner for it. DONE
work remains DONE as historical context and can be reopened deliberately.

### Inherited Updates

Concise Updates available at the snapshot are preserved as inherited context
with their original author and timestamp. They are distinguishable from new
Updates authored on the clone. The source Board's audit log is not copied; the
new audit log begins with the clone event and links back to the source
revision.

### No Automatic Synchronization

After cloning:

- later source Board changes do not appear automatically;
- clone changes do not modify the source;
- claims are isolated;
- Work Item state is independent;
- Board merging is not supported; and
- pulling or pushing Board changes is not supported.

Agents may query related Work Items by `lineage_id` to understand how sibling
strategies addressed the same originating work. That visibility does not imply
synchronization.

## Evaluation And Evidence Connections

Evaluation Runs should optionally connect to the Board from which they were
initiated.

This allows Studio and coding agents to answer:

- Which Runs were produced by this strategy?
- What did agents on this Board evaluate recently?
- Which Board produced this candidate?
- How did independent Board strategies compare?
- Which Runs support a Work Item's completion?

### Dataset Ownership

A Dataset does not belong to a Board. Datasets are reusable evaluation inputs
and may be shared across Boards, Projects, and strategies.

### Run Origin

An evaluation Run may record an optional originating `board_id` when started.
Its Project is derived through the Board.

A Run does not require one Work Item ID because:

- one Run may validate several Work Items;
- a baseline Run may be exploratory;
- one Run may reveal new failures not represented by existing items; and
- a Work Item may depend on several Runs.

Work Item Updates reference whichever Dataset, Run, Attempt, comparison,
execution, or commit is relevant. A Run with one originating Board may still
be referenced from another Board when that evidence is useful.

The relationship is:

```text
Board ── optional origin of ──> Evaluation Run
Work Item Update ── references ──> Dataset / Run / Attempt / execution
```

### Telemetry Boundary

Project, Board, Work Item, and claim identity do not need to be copied onto
every span.

The canonical relationship is already available through control records:

```text
Board → Run → Attempt → semantic execution → trace
```

The existing Attempt-to-execution evidence binding remains authoritative.
Board coordination does not change Studio ingestion, the OTLP hot path,
evaluation role spans, or the shared telemetry contract.

## Logical Data Model

The minimal logical entities are:

1. `Project`
2. `Board`
3. `WorkItem`
4. `WorkItemUpdate`
5. `WorkReference`
6. `AuditEvent`
7. current claim fields on `WorkItem`

`WorkReference` is the bounded association from an Update to an existing
commit, Dataset, Run, Attempt, comparison, or semantic execution. Its physical
database representation and exact discriminated contract belong in the future
implementation ADR.

A separate claim-history table is not required initially because current claim
state belongs on the Work Item and claim history is preserved by audit events.

## Agent-Facing Operations

The Python SDK remains the canonical programmatic implementation. A JSON-first
CLI is its adapter for coding agents and shell automation.

Conceptual operations are:

```text
junjo work projects list
junjo work projects get
junjo work projects create

junjo work boards list
junjo work boards get
junjo work boards create
junjo work boards clone

junjo work items list
junjo work items get
junjo work items create
junjo work items claim
junjo work items update
junjo work items release
junjo work items abandon
junjo work items reclaim
junjo work items move
junjo work items complete
junjo work items reopen

junjo work updates list
junjo work audit list

junjo work context show
junjo work context use
junjo work context clear
```

These names are illustrative, not accepted CLI syntax. The implementation
should preserve the same JSON-first, typed-error, SDK-owned approach already
used by Junjo Evaluation.

## Coding-Agent Skill Responsibilities

The distributable Junjo coding-agent guidance should teach an agent to:

1. inspect its worktree-local Project and Board context;
2. query Board Updates since the last observed cursor;
3. read the Board and Project descriptions before deciding where work belongs;
4. search the current Board before creating duplicate work;
5. join a shared Board when work should coordinate with other agents;
6. clone only for an intentionally independent approach;
7. claim a TODO atomically before implementation;
8. state when another update should be expected;
9. post concise substantive Updates rather than raw activity noise;
10. reference commits, evaluations, and evidence instead of copying them;
11. release or abandon work explicitly when stopping;
12. reclaim overdue work only through the audited operation;
13. attach candidate evidence before completing evaluation-backed work; and
14. check sibling lineage when comparing independent strategies.

A high-level developer request should be sufficient:

> Join the AI Chat improvement Board, review what changed since this worktree
> last checked, claim the first TODO, work on it locally, keep the Board
> updated, and attach evaluation evidence when it is done.

The developer should not have to copy Board IDs, claim IDs, Run IDs, cursors,
or command flags between agent messages.

## Authentication And Actor Identity

Audit and claim records distinguish:

- authenticated Studio user or developer token;
- coding-agent instance or session;
- human-readable worker label; and
- optional workspace or branch context.

For the first implementation, Projects and Boards may follow Studio's existing
deployment-shared resource model. Fine-grained Board ACLs, teams, and ownership
rules are deferred.

Developer automation requires an explicit control-plane authorization
decision. Dedicated work-read and work-write scopes are a reasonable
direction, but the future authentication and work-coordination ADRs must accept
the exact scope contract. Application Telemetry API keys never authorize this
control plane.

## User Stories

### US-K1: Organize Related Strategies

**As a developer or coding agent, I want named Projects and Boards with clear
descriptions so that I can understand how work is grouped and why separate
strategies exist.**

Acceptance:

- Project name and description are required.
- Board name and description are required.
- One Project may contain multiple Boards.
- The data model does not impose Board type rules.

### US-K2: Coordinate Parallel Agents

**As a coding agent, I want to share one Board from a separate worktree so that
I can see related work, avoid duplication, and claim one item safely.**

Acceptance:

- Multiple agents can read the same ordered TODO, DOING, and DONE columns.
- Claiming is atomic and returns explicit conflicts.
- Claim identity includes authenticated principal and agent instance.
- One active claim exists per Work Item.

### US-K3: Detect Abandoned Work

**As an agent or human, I want to see when a claimant missed its promised
update so that stalled work can be investigated or reclaimed deliberately.**

Acceptance:

- Claims record last activity and next expected update.
- Overdue status is derived and queryable.
- Overdue claims are never released automatically.
- Release, abandon, and reclaim are explicit audited actions.

### US-K4: Record Useful Progress

**As a collaborator, I want concise Work Item Updates containing attempts,
results, decisions, commits, and evidence links so that another agent can
continue without reconstructing the history.**

Acceptance:

- Updates are timestamped and actor-attributed.
- Updates can reference canonical commits and Studio evidence.
- Updates do not copy complete trace or source payloads.
- Updates are distinct from automatic audit events.

### US-K5: Review Board Activity

**As a coding agent, I want to query what changed on my Board since I last
checked so that I can understand other agents' progress before acting.**

Acceptance:

- The query uses a monotonic cursor.
- Results are grouped by Work Item.
- Current state and claim activity accompany recent Updates.
- The worktree-local context can retain the last observed cursor.

### US-K6: Work Independently

**As a coding agent, I want to create a separate Board for unrelated work or
an independent approach so that its priorities and decisions can diverge.**

Acceptance:

- Boards may be created in any Project chosen by the caller.
- Separate Boards have independent ordering and claims.
- A new worktree does not automatically create a Board.

### US-K7: Clone A Strategy

**As a coding agent, I want to clone a Board at one exact revision so that I can
explore an independent strategy from a known starting point.**

Acceptance:

- Clone creation is transactional.
- Source Board and source revision are recorded.
- Work Item lineage and evidence are preserved.
- DOING items become TODO and all claims are cleared.
- No later synchronization occurs.

### US-K8: Compare Related Approaches

**As a developer or coding agent, I want to find sibling Work Items across
cloned Boards so that I can compare how independent strategies handled the
same originating problem.**

Acceptance:

- Work Item lineage survives repeated cloning.
- Siblings are queryable by lineage ID.
- Querying lineage does not merge or synchronize Boards.

### US-K9: Remember Worktree Context

**As a coding agent, I want my local worktree to remember its active Project,
Board, claim, and latest-seen update position so that a new session can resume
without developer bookkeeping.**

Acceptance:

- Context is untracked and local to the worktree.
- Context is inspectable and replaceable.
- Explicit command or environment configuration can override it.
- Studio does not persist an absolute local filesystem path as Board identity.

### US-K10: Connect Work To Evaluation Evidence

**As a coding agent, I want evaluation Runs and Work Item Updates to retain
their Board and evidence context so that measured results explain why work was
created and whether it succeeded.**

Acceptance:

- A Run may record an optional originating Board.
- A Dataset is not owned by a Board.
- Updates may reference Datasets, Runs, Attempts, comparisons, executions, and
  commits.
- Board identity is not copied onto every telemetry span.

## Explicit Non-Goals

The initial strategy does not include:

- automatic Git worktree creation;
- branch creation or merging;
- source-file locking;
- task dependencies;
- Board merging;
- synchronization between cloned Boards;
- custom Board columns or workflows;
- Board types with enforced semantics;
- category or priority fields;
- target identity on Work Items;
- separate acceptance-criteria records;
- teams or fine-grained Board permissions;
- epics, sprints, estimates, velocity, or milestones;
- notifications;
- a general comments or chat system;
- a coding-agent process scheduler;
- automatic issue creation for every failed Attempt;
- automatic claim expiration or reassignment;
- telemetry duplication inside Work Items or Updates;
- automatic completion because a commit exists; or
- application code execution inside Studio.

## MVP Scope

The smallest useful implementation should include:

1. Projects with required names and descriptions.
2. Boards with required names, descriptions, revision, and optional clone
   lineage.
3. TODO, DOING, and DONE Work Items with relative ordering.
4. Atomic claim, release, abandon, and reclaim behavior.
5. Claim activity and caller-declared next update time.
6. Concise Work Item Updates with bounded references.
7. Append-only audit events committed with canonical state changes.
8. A cursor-based Board Updates query grouped by Work Item.
9. Worktree-local active context and latest-seen cursor.
10. Transactional Board cloning with deterministic state mapping and lineage.
11. Optional Board origin on evaluation Runs.
12. SDK client, JSON-first CLI, Studio Board UI, and coding-agent guidance.

No ingestion or Junjo Agent/Workflow runtime changes are required for this MVP.

## Roadmap Placement

Evidence-backed work coordination belongs after reliable evidence analysis and
before governed parallel improvement:

```text
Evaluation measurement and evidence
        ↓
Agent-assisted evidence analysis
Failure-mode identification and distillation
        ↓
Evidence-backed work coordination
Projects · Boards · Claims · Updates · Cloning
        ↓
Parallel coding-agent iteration
Shared and independent worktrees and strategies
        ↓
Governed promotion
```

This capability should receive its own implementation roadmap and ADR when it
becomes active work. It should not be inserted retroactively into the completed
Horizon 3 Lean MVP.

## Validation Application Demo

The accepted Kanban behavior should be demonstrated through a committed,
external-style sample application in which one coding harness coordinates two
parallel workers on a shared Board and one independent worker on a cloned
Board. The application should exercise a Junjo Workflow, a Junjo Agent,
application-local evaluations, telemetry, Work Item Updates, and evidence
links without making Studio responsible for source-code execution.

The complete application scenario, worker topology, validation layers, and
success criteria are owned by the
[Junjo Multi-Agent Kanban Validation Application Demo](AGENT_LAYER_KANBAN_MULTI_AGENT_VALIDATION_DEMO.md).

## Success Definition

The strategy succeeds when a developer can tell a coding agent:

> Join the AI Chat improvement Board, review what changed since this worktree
> last checked, claim the first TODO, work on it locally, post concise Updates,
> and attach evaluation evidence when it is done.

The agent can then:

1. recover the active Project and Board from local context;
2. read their purpose and collaboration strategy;
3. inspect recent work grouped by issue;
4. avoid or recognize overlapping claimed work;
5. claim one item atomically;
6. make source changes in its own worktree;
7. record findings, decisions, commits, and evaluation results concisely;
8. expose when it has stopped updating;
9. release, abandon, complete, or support explicit reclaiming of the work;
10. associate candidate Runs without moving application execution into Studio;
11. clone the Board when deliberately exploring a separate strategy; and
12. preserve an auditable relationship among the original problem, independent
    approaches, code changes, and measured results.

Junjo thereby provides shared improvement memory and coordination without
becoming a general project-management product, coding harness, source-control
system, or remote execution service.

# ADR 0016: Composable application Stores

- Status: Accepted
- Date: 2026-09-20
- Owners: Junjo platform
- Approval: implementation of the reviewed composable Store plan requested by the maintainer.

## Decision

An Agent may create its application Store through a definition factory or use
the live Store explicitly supplied to `execute(store=...)`. Workflows support
the same explicit borrowing argument. Tools receive the typed application
Store through `AgentRunContext.store`. Agents without application state remain
valid. Neither option implies a universal application ownership policy.

The private Agent runtime Store remains independent per invocation. Application
state does not replace transcripts, counters, usage, limits, or outcomes. Agent
results expose a detached `application_state` snapshot separately from output
and runtime diagnostics. Input, Tool output, and final model output mapping
remain explicit application code; sharing does not inject state into prompts.

Subflows continue creating isolated Stores and using their existing pre/post
actions. `parent_store` retains that mapping meaning. Graph instances, execution
identity, counters, and dispatcher snapshots remain independent even when
application state is shared. Execution-local context replaces a single mutable
Graph context on the Store. Hook registrations are not inherited or broadcast.
Existing Graph state-change callbacks remain Graph callbacks; this decision
does not add Agent application-state transition callbacks.

The existing Store lock orders atomic validated commits. It does not cover
model calls or complete executions. Stale read/replace actions may overwrite
each other; the application owns action semantics. No automatic merge,
transaction, conflict prevention, or execution concurrency limit is added.

## Evidence and telemetry contract 3

A Store has monotonic transition and revision counters. Each execution captures
its own start/end checkpoint under the Store lock. The checkpoint combines
detached state, its telemetry projection, and both counter positions. Replay
uses transitions in `(start_sequence, end_sequence]`, including sibling writes.
No-op actions advance sequence but not revision. Each mutation is emitted once
on the active span that performed it. Temporary SDK replay history is retained
only while an active execution boundary needs it.

Existing Workflow and private Agent boundary attributes retain their meanings.
They additionally emit `junjo.store.transition.start` and `.end`. Agent
application boundaries use `junjo.agent.application_store.id`, metadata under
`junjo.agent.application_store` (revision.start/end, transition.start/end/count,
reconstructable), and payloads `junjo.agent.application_state.start/end`.
`junjo.agent.application_state.available` distinguishes a configured application
Store from absence. Operation revision attributes still describe private runtime
state. Payload modes, JSON Patch semantics, and definition fingerprints do not
change.

The active semantic telemetry contract advances from 2 to 3 with coordinated
SDK and Studio consumers. Ingestion continues preserving attributes/events
without interpreting Store relationships. No storage columns, protobufs,
database migrations, or compatibility adapters are required.

The maintainer confirmed that this breaking upgrade requires discarding existing
Studio application data and initializing a fresh store. Old users, credentials,
evaluations, and telemetry are not migrated. Release preparation must follow the
[canonical reset procedure](../../apps/studio/deployments/RESET.md), publish a
matching SDK/Studio pair, and document the reset. No old-contract parser,
dual emission, compatibility shim, or automatic data conversion is introduced.

Studio represents Store identity separately from each executable's role and
interval. Shared references are valid; private runtime Stores remain exclusive.
Its reconstruction is authoritative and preserves missing/policy-unavailable
evidence. A reused Store can start at a nonzero checkpoint in a later trace.
Concurrent writes missing from the selected trace make replay incomplete;
sharing is still allowed, and cross-trace Store indexing is not introduced.

## Consequences

Agents, Workflow Nodes, ordinary Tools, and Workflow Tools can work on one
typed domain Store or map between separate Stores. Subflow semantics remain
stable. Result snapshots describe a boundary, not a promise that a live shared
Store will stop changing. Studio views and coding-agent evidence must select
execution plus Store role rather than infer one exclusive owner from Store ID.

This decision revises the application-state restrictions in ADRs 0003–0006
and Studio ADR 007. Their private runtime, model, lifecycle, payload, and
failure/cancellation contracts otherwise remain in force.

## Related

- [Implementation map](../roadmaps/COMPOSABLE_AGENT_APPLICATION_STORES.md)
- [Agent execution](0003-agent-execution-model.md)
- [Composition](0005-agent-workflow-composition.md)
- [Telemetry](0006-agent-telemetry-contract.md)

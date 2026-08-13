# Studio execution exploration correction

- Status: Completed
- Accepted: 2026-07-15
- Navigation clarification: 2026-08-12
- Scope: Studio execution deep links, Store diagnostic presentation, and
  Workflow Graph exploration

## Goal

Restore the original cohesive Workflow exploration behavior while preserving
the accepted Agent telemetry architecture. Remove implementation concepts that
leaked into product copy, make semantic deep links useful while telemetry is
still arriving, and protect the Mermaid integration from renderer changes.

## Implementation sequence

1. Revise the architectural decisions before code changes:
   - root ADR 0007 owns semantic execution-link readiness;
   - Studio ADR 007 owns Store integrity meaning and presentation;
   - Studio ADR 008 owns Graph/tree/state/URL selection.
2. Replace the bounded resolver holding screen with an immediate semantic
   execution page. Continue resolving 404 responses with capped backoff. Once
   ready, replace the semantic location with the ordinary physical detail URL
   so detail selection has one route authority.
3. Make healthy Store verification silent. Show focused notices only for
   partial, unavailable, failed, or unidentifiable state history.
4. Replace Mermaid-ID parsing with one DOM adapter and Junjo-owned rendered
   identities. Resolve highlights against each Graph snapshot so mixed
   Workflow/Agent ancestry behaves correctly.
5. Exact-pin Mermaid and add real-renderer and interaction acceptance tests.
6. Run frontend lint, tests, build, and the complete Studio validation suite.

## Required acceptance

- A fresh execution link immediately shows Studio content. The pending
  telemetry message appears only after Studio confirms that the execution is
  not yet indexed, with no attempt counter or deadline.
- The semantic URL remains stable while resolution is pending; the resolved
  Agent, Workflow, or trace URL owns navigation after evidence is available.
- Healthy Store history produces no banner; non-healthy states remain explicit
  without hiding raw telemetry.
- Graph click, tree click, Store transition navigation, Subflow activation, and
  URL restoration remain synchronized.
- Agent/model/tool spans inside a Workflow Node highlight that Node.
- Tests execute the installed Mermaid renderer and fail if its DOM can no
  longer be indexed.

Architecture belongs to the referenced ADRs; implementation details belong to
code and tests. This document is the bounded delivery record for the correction.

## Completion record

Completed on 2026-07-15 and navigation clarified on 2026-08-12. Frontend lint, 205 frontend tests, the production
build, and the complete six-stage Studio validation passed. The test suite uses
the installed Mermaid 11.16.0 renderer and covers semantic-link readiness,
quiet healthy Store diagnostics, normal Nodes, Subflows, RunConcurrent
clusters, bidirectional Graph/tree selection, URL selection, Store navigation,
and Agent/model ancestry inside a Workflow Node.

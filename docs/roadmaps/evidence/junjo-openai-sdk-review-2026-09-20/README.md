# OpenAI example and composable Stores: end-to-end review

Reviewed September 20, 2026 against the current working tree. The findings below
describe the initial review, before corrections. All four findings and the
related Raw trace navigation gap were subsequently fixed; see
[fixes and validation](FIXES.md). No production code was changed during the
initial review itself.

## Result

Execution, ingestion, reconstruction, and CLI/API parity passed. The actual
browser review found a shared-Store navigation bug and several presentation
and discovery gaps. Automated tests alone did not establish that the UX was
complete.

## Findings

### P2 — Directly selecting a nested mutation changes the execution interval

Location: `apps/studio/frontend/src/features/junjo-data/span-lists/FlatStateEventsList.tsx:143-154`.

Reproduction using the running local Studio:

1. Open [Support caller review](http://localhost:26151/workflows/junjo_openai_sdk/f560669c9eaf9d1543e1c4a30234e6a4/6593216b3c72388a).
2. Select **State Updates**. All four application mutations appear: order
   lookup, policy evaluation, eligibility decision, and the caller's subsequent
   decision update.
3. Click transition 2, `record_policy_evaluation`.
4. The navigation now says **1 / 2** and disables Previous. It silently switched
   to the child Workflow's `(1,3]` interval, while the page still identifies the
   calling Workflow. Next reaches transition 3 and stops, excluding the caller's
   fourth mutation.
5. Return to the caller URL, select transition 1, then press **Next Store
   transition**. The same transition 2 instead shows **2 / 4**, with Previous
   enabled. Reaching the same event by two controls produces different histories.

The row's selection omits `viewOwnerSpanId`, so
`selectWorkflowStoreViewOwner` follows the selected writer to the nearest
Workflow. The Next/Previous handler already preserves the view owner. Row
selection should preserve the execution view that supplied the displayed
transition, including the existing handling for writers outside the view's
physical descendants. Cover the row and Next/Previous paths in one interaction
regression test.

The backend retains all four mutations correctly; this is a frontend selection
issue, not lost telemetry.

### P2 — Agent state history has no navigation to the actual writer

Location: `apps/studio/frontend/src/features/agent-executions/components/AgentStateTimeline.tsx:160-163`.

In [the eligible Agent](http://localhost:26151/agents/4b24f5b074cb10a820841b672b7242f3/7d971351c840674f),
select `record_policy_evaluation` or `record_order`. The header shows an opaque
writer span ID as plain text. There is no writer link or writer name. The user
must leave for Raw trace and manually locate the responsible Node. This is
particularly awkward for the direct lookup Node, which has no child Workflow
diagnostics card. The Workflow state history already provides **View writer
span**; the Agent history needs the equivalent link using the existing trace
and span identities. No new backend contract is needed.

Related existing discovery gap: raw trace rows expose **Workflow Explorer** for
Workflows but no equivalent Agent diagnostics link. This was observed in the
browser and exists in `features/traces/SpanRow.tsx:39-54`; it is separate from
Store reconstruction.

### P2 — Nested null values are visually blank in Agent state evidence

Location: `apps/studio/frontend/src/components/SpanAttributeKeyValueViewer.tsx:51-56`.

The eligible Agent's policy transition has `eligible: null` and
`decision_reason: null` before and after policy evaluation. CLI/API JSON retains
those explicit nulls. The Agent before/after panels render the field name and
colon with no value. Its starting snapshot similarly hides all unset fields.
The Workflow state viewer displays `null` correctly for the same data.

The shared JSON viewer uses `displayDataTypes={false}`; with the installed
viewer this also suppresses the null value's display. This pre-existing renderer
behavior now affects the new application-state panels. Preserve explicit null
rendering without changing evidence data, and verify it with the actual viewer.

### P3 — Tool inspector still describes mandatory isolated state

Location: `apps/studio/frontend/src/features/agent-executions/components/AgentOperationTimeline.tsx:210-212`.

The eligibility Tool's child card says “Each child owns its own state and
diagnostics.” This example's Agent and Workflow use the exact same application
Store. Describe each child's execution diagnostics and boundary snapshots;
present shared and isolated Stores as options, consistent with ADR 0016.

## Live execution and evidence

The repository-local Compose stack was built and started from current source.
Existing local data and the unrelated Incinerator stack were retained. The
public local provisioning script was used; there was no host access to the live
Studio SQLite database.

The review harness imported the actual example's `application.py`, `driver.py`,
and `telemetry.py`. It used the real AsyncOpenAI SDK, OpenInference instrumentor,
Junjo runtime, Junjo OTLP exporter, gRPC ingestion, storage, backend projection,
and browser frontend. Only provider HTTP responses were replaced with
`httpx2.MockTransport`; no paid OpenAI calls occurred.

Four cases were authored and executed with the installed public Junjo CLI:

| Case | Store creation | Branch | Result |
| --- | --- | --- | --- |
| ORD-1001 | Agent factory | Eligible, 10 days | Passed |
| ORD-1001 | Caller supplies Store | Eligible, 10 days | Passed |
| ORD-1002 | Agent factory | Ineligible, 50 days | Passed |
| ORD-1002 | Caller supplies Store | Ineligible, 50 days | Passed |

Studio's [evaluation run](http://localhost:26151/evaluation-runs/ckeA5I1irielbCTa1D4ZrN)
shows the same four passes, zero failures, zero errors, and 100% pass rate as the
CLI. Each case's **View spans** resolves to its Agent execution.

Assertions after real ingestion, for every case:

- 16 spans, including the three evaluation spans, one Agent, three model-request
  operations, three OpenInference LLM spans, two Tool operations, one Workflow,
  and three Nodes.
- Each provider LLM span is a child of its own model-request operation.
- `LookupOrderNode` is directly beneath the lookup Tool, without a one-node
  Workflow wrapper.
- `ReturnEligibilityWorkflow` is directly beneath the eligibility Tool; its
  policy Node and the selected branch Node are its children.
- The Agent and Workflow share one application Store identity; the private
  Agent runtime Store has a different identity.
- Application mutations occur once, on their actual writer Nodes, with sequences
  1, 2, 3. Agent interval `(0,3]`; child Workflow interval `(1,3]`; private runtime
  interval `(0,13]`. All claimed reconstructions are verified, with no trace
  diagnostics.
- Final eligibility, Store state, Tool response, and typed final output agree.
  Normalized usage is 30 input tokens, 15 output tokens, 45 total tokens.
- CLI `attempt evidence full`, `manifest`, and selected `spans` responses equal
  the corresponding session-authenticated Studio API payloads exactly.

See [parity-report.json](parity-report.json) for trace, span, Store, attempt, and
resolution identities.

A fifth execution exercised **Workflow → Agent → Workflow**, borrowing one
live application Store and writing an explicit result back in the calling
Node. The caller's `(0,4]`, Agent's `(0,3]`, and child Workflow's `(1,3]` views all
reconstruct correctly. The caller's fourth mutation does not alter the Agent's
captured ending snapshot. Its state update list excludes the Agent's private
runtime mutations. See [composition-report.json](composition-report.json).

## Browser checks

Exercised the real development frontend at `http://localhost:26151`:

- Agent service query, completed execution selection, operation inspector,
  application and runtime histories, and normalized usage.
- Agent eligibility Tool → child Workflow diagnostics.
- Both conditional graph branches, executed/dimmed nodes, selection highlighting,
  graph → Node URL, tree selection, Before/After state, exact event selection,
  Previous/Next, and reload of a Node deep link.
- Unexecuted branch click leaves selection unchanged.
- Workflow state event → writer deep link → the exact writer's raw span.
- Raw trace tree visually preserves provider/model, Tool/Node, and Tool/Workflow
  parentage. Provider detail shows input, output, call IDs, tools, and token usage.
- Browser Back and Forward return to the correct Workflow/raw-span routes.
- Evaluation dataset → run → case **View spans** → resolved Agent diagnostics.
- Calling Workflow state list and nested writer selection (finding above).

The browser initially held an expired session from before startup. A normal
sign-in restored access. Console review subsequently showed no page crashes;
there were Redux selector stability warnings, which were not investigated as
performance regressions in this functional review.

## Automated checks run in this review

- Example integration suite: **4 passed**.
- Targeted frontend suites: **13 passed** across Agent request integration,
  Workflow Store transition navigation, and composable-Store hydration/rendering.
- Public CLI evaluations: **4 passed**.
- Full/manifest/selected CLI-versus-API equality: **4 cases passed**.
- Calling Workflow execution and reconstruction assertions: **passed**.

The full SDK/Studio/website checks had passed during implementation; they were
not rerun here because no production code changed. The new composable-Store
frontend test asserts hydration and the presence of both history regions; it
does not click their controls or exercise the failing flat-list selection path.
This explains why green automated tests did not catch this interaction bug.

## Limits and retained artifacts

This proves the integration path with deterministic provider responses. It does
not establish live OpenAI model behavior, production deployment behavior, mobile
layout, concurrent throughput, or every unrelated Studio navigation path.
Existing Subflow isolation was not exercised again in this browser review.

The temporary CLI harness had its own clean Git commit because evaluation
requires a clean committed application. The evaluation run's revision identifies
that temporary harness, not a commit of this uncommitted repository state.

The harness scripts and full responses were retained locally under
`/tmp/junjo-openai-sdk-review-20260920`. Compact, non-secret evidence is saved
alongside this report. The review's temporary telemetry key, CLI token, and user
were removed through public APIs; existing persistent development credentials
and the local stack remain available for inspecting these executions.

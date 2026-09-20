# Review fixes and validation

All four findings from the [initial review](README.md) are fixed in the working
tree, along with its related Raw trace → Agent navigation gap. The fixes use the
existing frontend evidence and routes; no SDK, ingestion, backend, API, or
telemetry contract changes were necessary.

## Changes

- The Workflow state list and Previous/Next controls now share one selection
  handler. Both preserve the execution interval that supplied the transition.
  The list resolves writer events from the whole trace, allowing sibling
  writers to remain selectable without inserting them into the current
  Workflow's Graph or URL. The list still displays only transitions from the
  backend's selected execution interval.
- Application and private Agent runtime transitions link to their exact writer
  span in Raw trace. Native Agent rows there link back to Agent diagnostics.
- The existing JSON viewer explicitly renders nested null values, including
  nulls inside arrays and serialized JSON objects. Other value rendering and
  evidence data are unchanged.
- The Tool inspector describes independent execution boundaries and diagnostics
  while explicitly allowing shared or separate application Stores.

## Regression tests

The new interval-selection test reproduced the incorrect child Workflow owner
before the fix. It verifies that direct row selection and Next reach the same
event with the same view owner, and that Previous can return across the child
boundary. The sibling-writer case now exercises both row and Next selection.

The null-rendering tests reproduced blank values using the installed JSON
renderer before the fix and now pass for object and serialized JSON evidence.
The composable-Store test now clicks application and runtime transitions and
follows their writer links. Raw trace tests cover both Workflow and Agent links
and verify that link navigation does not also trigger raw span selection.

## Validation results

`apps/studio/run-all-tests.sh` ran the complete Studio validation:

| Check | Result |
| --- | --- |
| Backend pytest | 964 passed, 2 existing skips |
| Rust ingestion | 40 passed |
| Frontend Vitest | 257 passed across 66 files |
| Frontend Node request-policy tests | Passed |
| Python lint and formatting | Passed |
| Frontend ESLint | Passed |
| REST API contract validation | Passed, 31 frontend contract tests |
| Proto regeneration/staleness | Passed |
| TypeScript and Vite production build | Passed after the test correction below |

The full runner initially reported the frontend build as failed because a new
Testing Library `getByRole` call incorrectly included Playwright's `exact`
option. The string matcher is already exact in Testing Library; removing that
unsupported option corrected the test typing. The affected integration test
and complete production build were rerun successfully. The other checks had
already passed. Vite retains its existing large-chunk warning.

The frontend suite includes the actual installed Mermaid renderer and the
Graph/tree/state/URL interaction tests, plus Workflow-detail and shared-Store
navigation coverage. `git diff --check` is clean.

## Live browser verification

Used the same real-ingestion traces recorded in the original review and the
current development frontend. No new provider calls or test credentials were
needed.

- In **Support caller review**, directly clicking mutation 2 now shows **2 / 4**.
  Next reaches **3 / 4** and then the calling Node's **4 / 4** mutation, with the
  correct writer span in the URL and the parent Graph highlighted. This is the
  exact interaction that previously switched to **1 / 2**.
- The Agent policy transition visibly renders explicit `null` values for unset
  fields in Before and After. Its writer link opens
  `EvaluateReturnPolicyNode`, span `33e0f4cda149b132`.
- The direct lookup mutation links to `LookupOrderNode` without a Workflow
  wrapper. Private runtime transitions also expose their actual writer links.
- Raw trace's **Agent diagnostics** link returns to the same Agent execution.
- The eligibility Tool card displays the corrected shared/separate Store
  wording.

These are presentation and selection fixes over the already verified evidence.
The original four-case CLI/API parity results and span-parentage checks remain
applicable; these changes do not alter their payloads or producers.

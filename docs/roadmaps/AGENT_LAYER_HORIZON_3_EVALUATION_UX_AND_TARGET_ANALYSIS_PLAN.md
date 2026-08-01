# Horizon 3 Binary Evaluation UX And Scope Plan

- Status: Implemented and validated
- Date: 2026-07-29
- Owners: Junjo platform
- Foundation:
  [Horizon 3 Evaluation Lean MVP](AGENT_LAYER_HORIZON_3_LEAN_EVALUATION_MVP.md)
- Product requirements:
  [Horizon 3 Evaluation Product User Stories](AGENT_LAYER_HORIZON_3_EVALUATION_USER_STORIES.md)
- Architectural decisions:
  [ADR 0013](../adr/0013-application-executed-studio-evaluations.md),
  [ADR 0014](../adr/0014-evaluation-telemetry-context.md), and
  [Studio ADR 010](../../apps/studio/docs/adr/010-evaluation-control-persistence-and-api.md)

## Purpose

The evaluation control plane is mechanically complete, but its first result
browser exposed machine terminology and an unnecessary numeric score model.
This plan defines the small product correction required before the evaluation
UX is reviewed as a user-facing system.

The correction is intentionally subtractive:

- evaluation judgments are binary;
- Node, Workflow, or Agent scope is prominent;
- a human evaluation name explains what pass or fail tests;
- machine Case keys and evaluator dispatch identities become technical detail;
- Git commit provenance moves out of list tables;
- Dataset membership becomes directly inspectable; and
- every result has one concise **View spans** action.

No ingestion, OTLP, Parquet, telemetry-contract, scheduler, evaluator service,
analytics database, or trace-copying change is part of this work.

## Product Model

Use these terms consistently:

| Product term | Meaning |
| --- | --- |
| Dataset | One immutable ordered collection of Tests |
| Test | One input, pass condition, evaluation name, and execution scope |
| Scope | The Node, Workflow, or Agent executed by a Test |
| Run | One labeled execution of a locked Dataset from one Git commit |
| Result | One Test's binary judgment or operational error within a Run |
| Evaluation | The human-named criterion that determines pass or fail |
| Spans | The complete telemetry received for the exact Test execution |

The persisted `case_key`, evaluator key/version, input version, IDs, and source
provenance remain necessary machine contracts. They are not primary product
labels.

Baseline and candidate are comparison roles assigned to two Runs. They are not
persisted entity types. Every Run therefore stores `run_label`, not
`candidate_label`.

## Binary Result Contract

Every application evaluator returns:

```text
passed: boolean
reason: non-empty bounded text
```

Studio stores Attempt lifecycle as:

```text
queued | passed | failed | error
```

`error` is an operational failure, not a failed quality judgment.

The product does not store or display:

- numeric score;
- mean score;
- score delta;
- confidence;
- weighting; or
- automatic promotion thresholds.

Aggregate semantics remain:

```text
total = queued + passed + failed + error
judged = passed + failed
pass_rate = passed / judged, or null when judged == 0
coverage = judged / total, or null when total == 0
```

Errors and queued Results are always shown beside pass rate.

## Evaluation Name

Every immutable Test stores a required `evaluation_name`, for example:

```text
Response place realism
```

The evaluation name describes what the binary judgment means. The Case's
`expectation_json` contains the exact pass condition or rubric. The
application's evaluator key/version identifies the code that applies it.

This remains one Case record. Do not add an evaluator registry, Evaluation
table, rubric DSL, or remotely executed evaluator.

## Dataset Experience

Dataset names are links. A Dataset detail page uses the existing bounded
Dataset-detail API and shows:

- name, description, application, and draft/locked status;
- ordered Tests;
- each Test's evaluation name;
- prominent Node, Workflow, or Agent scope;
- input;
- pass condition or rubric;
- authored/generated origin;
- generated-source provenance when present; and
- Run history.

Machine Case key, input/evaluator versions, source IDs, and timestamps belong
in technical details.

## Evaluations Landing Page

The landing page is Dataset-first.

Primary controls:

```text
Dataset:    Local place realism
Scope:      All | Node / turn.date_response | Workflow / turn | Agent / chat
Evaluation: All | Response place realism
```

Run history uses:

| Run | Scope | Results | Status | Created |
| --- | --- | --- | --- | --- |
| prompt-v3 | Node · Workflow · Agent | 8 passed · 2 failed · 1 error | Completed | time |

Do not show Git commits, Dataset IDs, Run IDs, evaluator versions, or machine
Case keys in this table.

The selected Dataset heading links to Dataset detail.

## Run Detail

The Run header shows:

- Run label;
- linked Dataset name;
- lifecycle status;
- result counts and pass rate; and
- Git commit under the exact label **Git Commit**.

The primary result table is:

| Scope | Evaluation | Result | Reason | Spans |
| --- | --- | --- | --- | --- |
| Node · `turn.date_response` | Response place realism | Passed | concise reason | View spans |

Scope is visually prominent. Result rows default to errors and failures first.

The primary span action is exactly **View spans**. It follows the existing
semantic execution resolver to the canonical Workflow or Agent detail page.
A Node Test resolves to its truthful one-Node Workflow execution.

Generated-source spans belong in expandable provenance, not beside the
primary Result span link.

## Comparison

The user selects two completed Runs from the same locked Dataset. The UI calls
them Baseline and Candidate only inside the comparison.

Transitions are status-only:

| Baseline | Candidate | Classification |
| --- | --- | --- |
| failed | passed | improved |
| passed | failed | regressed |
| passed/failed | error | newly errored |
| error | passed/failed | recovered |
| same status | unchanged |
| otherwise | changed |

Comparison rows show:

- prominent Scope;
- Evaluation name;
- baseline and candidate result;
- both reasons;
- **View baseline spans**; and
- **View candidate spans**.

There are no score columns or deltas. Git commits remain available by opening
the Run details.

## Data And Contract Changes

The greenfield evaluation schema changes together:

1. rename Run `candidate_label` to `run_label`;
2. add required Case `evaluation_name`;
3. remove Attempt `score`;
4. remove outcome-summary `mean_score`;
5. remove comparison `score_delta`;
6. replace evaluator-facing list scope with human `evaluation_name`;
7. regenerate the one initial migration; and
8. reset local application data.

The SDK and CLI change together:

- `EvaluationResult(passed, reason)`;
- `--run-label`;
- required `--evaluation-name` for authored and generated Cases;
- binary built-in and callback evaluators;
- binary comparison projections; and
- updated JSON contracts, docs, examples, and coding-agent skill.

The AI Chat reference changes together:

- `QualityJudgment(passed, reason)`;
- a strict binary judge prompt;
- `Response place realism` Test metadata; and
- recreated Node, Workflow, and Agent Dataset records.

## Validation

The implementation is complete only when:

1. the generated initial migration upgrades, passes `alembic check`,
   downgrades, and upgrades again;
2. backend repository and router tests prove binary terminal invariants,
   evaluation-name filtering, aggregates, and idempotency;
3. SDK tests prove binary evaluators, Run labels, Case evaluation names,
   resume, comparison, CLI JSON, and OpenAPI parity;
4. frontend tests prove Dataset navigation, prominent scope, hidden machine
   keys, Git Commit detail placement, binary comparison, and span link labels;
5. Studio and SDK full validation suites pass;
6. the local greenfield data is wiped and the current Compose images rebuilt;
7. AI Chat creates a locked Dataset with Node, Workflow, and Agent Tests named
   `Response place realism`;
8. at least two Runs produce comparable binary Results;
9. every **View spans** action resolves to the exact received execution; and
10. the resulting Chrome UX is ready for attended post-evaluation review.

## Completion Record

Implementation and validation completed on 2026-07-29.

- Studio's local data was deleted and rebuilt from the single generated
  greenfield migration `65bb30ac331d`. Upgrade, downgrade, re-upgrade, and
  `alembic check` all passed.
- Studio's aggregate validation passed: Ruff; 951 backend tests with 3 skips;
  37 ingestion tests; 249 frontend tests; 32 REST contract tests; frontend
  production build; and proto-staleness validation.
- The Python SDK passed Ruff, 380 tests, strict `ty`, Griffe public-surface
  validation, package build, and Twine validation. AI Chat passed 60 backend
  tests plus 27 frontend tests, lint, and production build.
- The installed-wheel standalone E2E created and compared a three-Test
  Node/Workflow/Agent Dataset, exported OTLP telemetry, resolved every Result
  to received evidence, and revoked its temporary Evaluation token.
- AI Chat created the locked `local-place-realism-v1` Dataset with three Tests
  named **Response place realism** across Node `turn.date_response`, Workflow
  `turn`, and Agent `chat`.
- The `baseline` and `current` Runs completed six of six binary judgments as
  passed. All six Results resolved to distinct received traces with no evidence
  diagnostics: 7 spans per focused Node execution, 13 per Workflow, and 7 per
  Agent.
- Chrome validation covered Dataset selection, readable Dataset inputs and
  pass conditions, Run history, Git Commit placement, binary Results, filters,
  comparison, and semantic **View spans** navigation. The attended Studio
  session remains signed in on the recreated Dataset.

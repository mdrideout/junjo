---
title: "Studio-Connected Evaluation"
---

Junjo Evaluation is the batteries-included loop for building typed input
datasets in Junjo AI Studio, executing them against the real application code
in your checkout, and comparing structured results with the exact traces
Studio received.

The application remains the execution host because it owns prompts, provider
credentials, Tools, databases, and domain services. The Junjo SDK owns the
Studio client, dataset and result DTOs, target lifecycles, evaluator contracts,
sequential executor, resume behavior, telemetry context, evidence queries, and
the `junjo eval` CLI.

For a developer with a configured application harness, the intended interaction
is a product-quality request to a coding agent:

> Use Junjo to create and run a baseline evaluation of our assistant's ability
> to recommend authentic local places. Store the dataset and results in Studio,
> inspect the failed cases and their traces, and report what should improve. Do
> not change the application yet.

The coding agent discovers the application's targets and evaluator schemas,
authors representative inputs and schema-valid expectations, operates the CLI,
tracks Studio identifiers, retrieves evidence, and reports results. With an LLM
judge, the expectation is a binary decision rubric rather than an expected
prose answer. The developer does not need to create JSON files, copy IDs, choose
CLI flags, or poll telemetry evidence.

## What belongs where

| Owner | Responsibility |
| --- | --- |
| Application | Typed inputs, real dependency construction, Node/Workflow/Agent factories, output projection, and domain-specific evaluator meaning |
| Junjo SDK | `EvaluationHarness`, targets, evaluators, Studio transport, Attempt lifecycle, evidence binding, resume, comparison, and CLI |
| Junjo AI Studio | Canonical datasets, cases, runs, attempts, results, evidence membership, and received trace evidence |

Studio never executes uploaded source code. Complete telemetry still enters
Studio through authenticated OTLP; evaluation REST operations store only
bounded control records and exact evidence references.

## Credentials stay separate

Sign in to Studio, open **Access Tokens**, choose the required scopes and
expiration, and create a developer access token. Copy it to the environment:

```dotenv
JUNJO_AI_STUDIO_BACKEND_BASE_URL=http://localhost:26154
JUNJO_AI_STUDIO_CLI_TOKEN=jcli_...
```

The access token has explicit `evaluation:read`, `evaluation:write`, and
`evidence:read` scopes. It cannot deliver OTLP telemetry. The existing
`JUNJO_AI_STUDIO_API_KEY`, created from **API Keys**, remains an
application-telemetry-only credential and cannot query or mutate datasets.

Remote Studio origins must use HTTPS. Explicit loopback development may use
HTTP.

## Give a coding agent the runbook

The installed Junjo wheel ships an Agent Skills-compatible
`junjo-evaluation` skill. Locate the exact skill matching the installed SDK:

```bash
junjo eval skill path
```

The command requires no application harness, Studio connection, or credential.
Its versioned JSON response contains the absolute skill directory and
`SKILL.md` path. Point the coding agent's normal skill installer at that
directory once.

Installing the Python package does not silently activate a coding-agent skill.
The explicit installation keeps agent configuration under the application
developer's control while the versioned skill, SDK, CLI, and documentation
remain owned and released together by Junjo.

After installation, a normal request should contain intent rather than Junjo
mechanics:

> Use Junjo to evaluate whether this workflow extracts complete invoice data.
> Establish a baseline in Studio and explain the failures from their traces.

For an improvement iteration:

> Improve refund-answer accuracy using our existing Junjo dataset, then compare
> the candidate with the baseline.

The skill owns discovery, scenario design, temporary schema-valid artifacts,
dataset operations, execution, evidence queries, and product-oriented
reporting. It asks the developer only for a real missing prerequisite,
materially ambiguous product intent, or authority to modify and commit code.

## Declare one harness

An application exports exactly one explicit `EvaluationHarness` object:

```python
from contextlib import asynccontextmanager

from junjo.evaluation import (
    EvaluationHarness,
    ExactMatchEvaluator,
    ExecutionServiceIdentity,
    NodeInvocation,
    NodeTarget,
)

@asynccontextmanager
async def evaluation_runtime():
    provider = build_provider()
    try:
        yield provider
    finally:
        await provider.close()

async def create_node(input_value, context, provider):
    return NodeInvocation(
        node=CreateAnswerNode(provider),
        store=AnswerStore(
            initial_state=AnswerState(question=input_value.question),
        ),
    )

def project_answer(result, input_value, context, provider):
    return result.state.answer

harness = EvaluationHarness(
    application_key="my_application",
    service_identity=ExecutionServiceIdentity(
        service_namespace="my_company",
        service_name="my_application",
    ),
    targets=(
        NodeTarget(
            key="answer",
            name="Create Answer Node",
            input_version=1,
            input_type=AnswerInputV1,
            factory=create_node,
            projector=project_answer,
        ),
    ),
    evaluators=(ExactMatchEvaluator(),),
    runtime_context=evaluation_runtime,
)
```

Configure the import explicitly in the application repository:

```toml
[tool.junjo.evaluation]
harness = "my_application.evaluation:harness"
```

`junjo eval targets list` returns each stable target key, its human-readable
Node, Workflow, or Agent name, and its JSON input schema. The CLI records that
name with authored and generated cases so Studio can label historical results
without presenting the dispatch key as an entity name. `junjo eval evaluators
list` returns stable evaluator identities, roles, and JSON expectation schemas.
Both import the harness without entering `evaluation_runtime`, so discovery
does not create providers, connect to application databases, or start
telemetry.

The runner verifies that a case's stored target name still matches its
registered target. Renaming a target therefore requires a new dataset rather
than silently relabeling immutable historical tests.

`NodeTarget`, `WorkflowTarget`, and `AgentTarget` own the correct public Junjo
lifecycle. Their application factories receive typed input, immutable
`EvaluationContext`, and the executor-owned application runtime. Factories may
attach an optional per-invocation cleanup callback; Junjo runs it even when
subject execution or projection fails.

The complete provider-free standalone declaration is in
[`examples/evaluation_standalone`](https://github.com/mdrideout/junjo/tree/master/sdks/python/examples/evaluation_standalone).
AI Chat is the full live-provider reference application.

## Author a dataset

Case input and expectation are JSON files or standard input. Secrets are never
ordinary command arguments.

```bash
junjo eval dataset create \
  --key answer-quality-v1 \
  --name "Answer quality"

junjo eval dataset add \
  --dataset-id DATASET_ID \
  --case-key question-1 \
  --evaluation-name "Answer exact match" \
  --target-kind node \
  --target-key answer \
  --input-version 1 \
  --input input.json \
  --expectation expectation.json \
  --evaluator-key junjo.exact \
  --evaluator-version 1

junjo eval dataset lock --dataset-id DATASET_ID
```

Locking is explicit and irreversible. Before requesting the lock, the CLI
validates every Case against the loaded target and evaluator declarations.
Studio preserves exact ordered membership for baseline/candidate comparison.

Built-in evaluators intentionally stay small:

- `ExactMatchEvaluator` compares a projected subject with
  `{"expected": ...}`.
- `StructuredFieldEvaluator` checks explicit top-level fields.
- `BooleanPredicateEvaluator` adapts a typed application predicate.
- `CallbackEvaluator` runs a bounded domain judge and requires the common
  `EvaluationResult`.

Applications can define domain meaning without owning Attempt transitions or
Studio writes.

## Generate a case through real execution

Dataset generation runs the same declared Node, Workflow, or Agent and records
its clean source revision plus exact semantic execution identity:

```bash
junjo eval case generate \
  --dataset-id DATASET_ID \
  --case-key generated-question-1 \
  --evaluation-name "Answer quality" \
  --target-kind workflow \
  --target-key answer-flow \
  --input-version 1 \
  --input input.json \
  --expectation expectation.json \
  --evaluator-key answer.quality \
  --evaluator-version 1
```

The observed subject is evidence only. Junjo never copies it into the expected
answer or silently promotes it to truth.

## Execute, resume, and compare

Run a locked dataset from a clean committed checkout:

```bash
junjo eval run execute \
  --dataset-id DATASET_ID \
  --request-key baseline-20260727 \
  --run-label baseline

junjo eval run resume --run-id RUN_ID
```

`EvaluationExecutor` executes sequentially. It lazily enters the application's
runtime context once, reuses that telemetry/provider/client runtime across
generated cases and Runs, and cleans each invocation explicitly. It validates before provider work,
pre-creates Studio Attempts, binds the exact subject execution before
judgment, and writes one terminal result.

Resume skips terminal Attempts. A queued Attempt with an already bound subject
is not executed again; it is finalized as interrupted, and a new Run is the
explicit subject-retry boundary.

After a committed prompt or implementation change, execute the same locked
Dataset with a new request key, then compare exact Case IDs:

```bash
junjo eval run compare \
  --baseline-run-id BASELINE_RUN_ID \
  --candidate-run-id CANDIDATE_RUN_ID \
  --target-kind node \
  --target-key answer \
  --input-version 1 \
  --evaluation-name "Answer quality"
```

Omit the target and evaluation flags to compare the complete Dataset. Run-list
queries accept the same exact Case scope:

```bash
junjo eval run list \
  --dataset-id DATASET_ID \
  --target-kind node \
  --target-key answer \
  --input-version 1 \
  --evaluation-name "Answer quality"
```

Studio and the SDK report `pass_rate` over judged Attempts only
(`passed / (passed + failed)`) and report coverage separately
(`judged / total`). Comparisons classify each immutable Case as `improved`, `regressed`,
`newly_errored`, `recovered`, `unchanged`, or `changed`, while retaining both
exact execution links.

## Query exact evidence

Control reads return bounded summaries. Complete trace evidence is hydrated
only when requested:

```bash
junjo eval run get --run-id RUN_ID
junjo eval attempt get --attempt-id ATTEMPT_ID
junjo eval attempt evidence --attempt-id ATTEMPT_ID
junjo eval evidence membership \
  --kind junjo_execution \
  --executable-type workflow \
  --runtime-id WORKFLOW_RUN_ID
```

Normal ingestion/indexing delay has a distinct pending-evidence error. An
ambiguous semantic execution identity is a conflict, not an arbitrary first
match.

The Python API uses the same implementation:

```python
from junjo.evaluation import EvaluationExecutor
from junjo.studio import StudioClient

async with StudioClient(base_url=studio_url, token=studio_token) as studio:
    async with EvaluationExecutor(client=studio, harness=harness) as evaluation:
        baseline = await evaluation.run(
            dataset_id=dataset_id,
            request_key="baseline-1",
            run_label="baseline",
        )
        candidate = await evaluation.run(
            dataset_id=dataset_id,
            request_key="candidate-2",
            run_label="more-specific-prompt",
        )
```

`EvaluationExecutor` is one application-host lifetime. It acquires the
application runtime only before real target execution, reuses process-global
telemetry and provider clients across iterative Runs and generated Cases, and
closes them once on exit. `StudioClient` is an async context manager with one
bounded HTTP connection pool, explicit timeouts, bounded response sizes, typed
errors, and opt-in evidence hydration.

## Telemetry classification

Evaluation execution retains the application's real OpenTelemetry Resource.
Junjo adds one bounded orchestration span and role spans:

- `junjo.evaluation.attempt`
- `junjo.evaluation.dataset_generation`
- `junjo.evaluation.subject`
- `junjo.evaluation.judge`
- `junjo.evaluation.verifier`

The spans carry `junjo.evaluation.*` Dataset, Run, Case, Attempt, source
revision, class, and role attributes. Junjo does not copy this metadata onto
every descendant model, Tool, Node, or Store span. Studio's Attempt-to-
evidence binding remains the canonical result/evidence join.

## Machine contract and low-resource defaults

Every CLI command writes one versioned JSON envelope to standard output.
Diagnostics go to standard error. Important exit statuses are:

| Status | Meaning |
| --- | --- |
| `0` | Command completed and no Attempt failed |
| `2` | Usage, local schema, or declaration error |
| `3` | Authentication or authorization failure |
| `4` | Immutable/idempotency or identity conflict |
| `5` | Subject or Attempt execution error |
| `6` | Evaluation completed with a failing judgment |
| `7` | Exact evidence is not ready |
| `8` | Studio remained transiently unavailable |
| `9` | Studio response is incompatible with the SDK contract |

Pages and responses are bounded, comparison uses summaries, evidence is
explicit, and concurrency defaults to one. Evaluation control adds no query,
cache, database lookup, or protocol to the Rust OTLP ingestion hot path.

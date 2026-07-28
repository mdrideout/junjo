---
name: junjo-evaluation
description: Build and run Junjo Studio-backed evaluation datasets against application-owned Node, Workflow, or Agent targets. Use when a coding agent needs to author or generate cases, execute or resume a dataset, inspect bounded trace evidence, compare candidate runs, or implement an application evaluation harness with the Junjo Python SDK.
---

# Junjo Evaluation

Use Junjo's installed SDK and `junjo eval` CLI to run a repository-local
evaluation harness against datasets stored in Junjo AI Studio. The application
owns its domain inputs, target factories, and evaluators. The SDK owns the
Studio client, control flow, telemetry context, and result contracts.

## Boundaries

- Use `junjo.evaluation`, `junjo.studio`, and the installed `junjo eval` CLI.
- Do not copy Studio clients, runners, DTOs, or generic evaluation mechanics
  into the application repository.
- Do not query Studio's observability REST routes directly. Use the bounded
  evidence and comparison methods exposed by the SDK and CLI.
- Keep `JUNJO_AI_STUDIO_CLI_TOKEN` separate from
  `JUNJO_AI_STUDIO_API_KEY`. The CLI token is a scoped control-plane
  credential; telemetry still travels through OTLP using the application's
  ingestion API key.
- Preserve the application's truthful OpenTelemetry service namespace and
  service name. Do not invent a special service identity for evaluation runs.
- Require an explicit `module:object` harness declaration. Generated target
  output is evidence for an authored case, not the source of truth for the
  application's target contract.
- Execute the MVP runner sequentially. Do not add application-local concurrency
  around evaluation attempts.

## 1. Inspect capabilities and targets

Run these before changing datasets:

```bash
junjo eval capabilities
junjo eval targets list
```

The CLI discovers the harness from:

```toml
[tool.junjo.evaluation]
harness = "my_app.evals:harness"
```

Alternatively, pass `--harness my_app.evals:harness` immediately after
`junjo eval`.

## 2. Declare application-owned targets

Create one `EvaluationHarness` in application code. Register the narrowest
useful target:

- `NodeTarget` for one directly executable Node.
- `WorkflowTarget` for an end-to-end or subflow boundary.
- `AgentTarget` for one Agent invocation.

Each target declares a stable key, an input schema version, a strict Pydantic
input model, a factory that constructs the real application object, and a
projector that returns the subject evaluated by the case's evaluator.

Use the harness's async runtime context for process-lifetime telemetry, model
providers, and database pools. One `EvaluationExecutor` enters it lazily and
reuses it across generated cases and Runs until the executor closes. Create
mutable case-specific state inside each target factory. Return a cleanup
callback when the factory creates temporary state.

Register application-owned evaluators with stable keys and versions. Evaluator
expectation models must be strict and versioned just like target inputs.

## 3. Configure Studio access

Set credentials outside source control:

```bash
export JUNJO_STUDIO_URL="https://api.example.com"
export JUNJO_AI_STUDIO_CLI_TOKEN="junjo_eval_..."
```

Sign in to Studio, open **Evaluation tokens**, and create the token with only
the scopes required by the workflow:

- `evaluation:read` to list datasets, runs, attempts, and comparisons.
- `evaluation:write` to create datasets/cases and execute runs.
- `evidence:read` to resolve attempt trace evidence.

Never print or persist the full token. Studio displays it only once.

## 4. Author or generate a dataset

Create a dataset, then add explicit JSON inputs:

```bash
junjo eval dataset create \
  --key local-place-realism \
  --name "Local place realism"

junjo eval dataset add \
  --dataset-id DATASET_ID \
  --case-key coffee-shop \
  --target-kind workflow \
  --target-key chat.turn \
  --input-version 1 \
  --input ./evals/cases/coffee-shop.input.json \
  --expectation ./evals/cases/coffee-shop.expectation.json \
  --evaluator-key text-quality \
  --evaluator-version 1
```

Use `junjo eval case generate` only when real application telemetry already
contains the execution that should seed the case. Review the bounded generated
input and expectation before locking the dataset.

Locking validates every case against the current harness:

```bash
junjo eval dataset lock --dataset-id DATASET_ID
```

## 5. Execute from a clean source tree

The runner records source provenance and rejects dirty source trees:

```bash
junjo eval run execute \
  --dataset-id DATASET_ID \
  --request-key prompt-v2-001 \
  --candidate-label "prompt-v2"
```

If a process stops after Studio created the run, resume it:

```bash
junjo eval run resume --run-id RUN_ID
```

Do not create a replacement run for the same interrupted request. The
`request-key` is the idempotency boundary.

## 6. Inspect bounded evidence

Start with the attempt and its resolved execution:

```bash
junjo eval attempt get --attempt-id ATTEMPT_ID
junjo eval attempt evidence --attempt-id ATTEMPT_ID
```

Evidence may be temporarily pending while telemetry is ingested and indexed.
Treat exit status `7` as retryable pending evidence, not a failed evaluation.

Use execution membership only when tracing upstream or downstream impact from
a known semantic execution identity:

```bash
junjo eval execution membership \
  --executable-type workflow \
  --runtime-id WORKFLOW_RUNTIME_ID
```

## 7. Compare and iterate

Compare two completed runs of the same locked dataset:

```bash
junjo eval run compare \
  --baseline-run-id BASELINE_RUN_ID \
  --candidate-run-id CANDIDATE_RUN_ID
```

Use the comparison plus bounded trace evidence to identify the first meaningful
behavior change. Modify application code or prompts, commit the source change,
execute the same locked inputs with a new request key and candidate label, and
compare again.

## Exit statuses

- `0`: command succeeded and all evaluated cases passed.
- `2`: CLI usage, local configuration, dirty source, or harness contract error.
- `3`: authentication or authorization failure.
- `4`: conflict or ambiguous execution identity.
- `5`: target or subject execution failed.
- `6`: evaluator execution failed or a judgment failed.
- `7`: evidence is not available yet.
- `8`: Studio is temporarily unavailable.
- `9`: SDK and Studio contracts are incompatible.

Every command writes one versioned JSON envelope to stdout. Diagnostics go to
stderr. Consume the envelope rather than parsing human prose.

## Completion report

When finishing an evaluation task, report:

- harness and target used;
- locked dataset ID and case count;
- source commit, run ID, and candidate label;
- pass/fail/error counts;
- baseline comparison when applicable;
- evidence still pending or any contract/authentication blocker.

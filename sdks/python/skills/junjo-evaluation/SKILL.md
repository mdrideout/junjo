---
name: junjo-evaluation
description: Turn a developer's product-quality objective into a complete Junjo Studio-backed evaluation workflow. Use when a coding agent needs to establish a baseline, design or generate typed cases, run or resume application-owned Node, Workflow, or Agent targets, inspect outcomes and exact trace evidence, compare a candidate with a baseline, improve evaluated behavior, or add an EvaluationHarness using the installed Junjo Python SDK.
---

# Junjo Evaluation

Operate Junjo Evaluation from the application repository using the installed
`junjo` SDK and CLI. Do not require access to the Junjo source repository.

## Operating contract

Treat a product-quality objective such as “evaluate local-place realism” as
sufficient direction to operate the complete baseline workflow. Own target and
evaluator discovery, scenario design, temporary JSON artifacts, Studio dataset
operations, run execution, identifier tracking, evidence retrieval, analysis,
and the final report.

Do not ask the developer to write JSON, choose CLI flags, copy identifiers,
poll evidence, or run commands. Ask only when product intent is materially
ambiguous or a real prerequisite or authorization is missing.

For a baseline request, measure current committed behavior and do not modify
application behavior. Modify prompts or code, run tests, or create commits only
when the developer authorizes an improvement iteration. Never commit unrelated
work.

## Boundaries

- Use `junjo eval explain` as the installed command, configuration, and output
  reference. Use the current command `--help` for exact syntax. Do not
  reproduce CLI mechanics with ad hoc HTTP or shell clients.
- Use `junjo.evaluation` and `junjo.studio` when application code or direct
  Python integration is required. Do not copy Studio clients, DTOs, runners, or
  generic evaluation mechanics into the application.
- Keep `JUNJO_AI_STUDIO_CLI_TOKEN` separate from
  `JUNJO_AI_STUDIO_API_KEY`. Never print, persist, or pass either secret as a
  routine command argument.
- Preserve the application's real OpenTelemetry service identity. Evaluation
  classification augments ordinary application telemetry; it does not create a
  fake evaluation service.
- Use bounded SDK/CLI evidence and comparison queries rather than Studio's raw
  observability routes.
- Let Junjo execute Attempts sequentially. Do not add application-local
  concurrency around the runner.

## 1. Inspect the application

Read the application repository's instructions and locate its configured
environment without exposing secrets. Inspect the nearest code, prompts,
fixtures, tests, and domain rules relevant to the requested quality objective.

Discover the harness through `[tool.junjo.evaluation].harness` in
`pyproject.toml` or an explicitly supplied `module:object`. Then inspect the
live machine contracts:

```bash
junjo eval capabilities
junjo eval explain
junjo eval targets list
junjo eval evaluators list
junjo eval --help
```

If no harness exists and the developer asked to set up Junjo Evaluation,
implement the narrow application-owned declaration with public
`junjo.evaluation` APIs. When the application uses the OpenAI Agents SDK and
needs an outer-Agent target, use the optional APIs installed by
`junjo[openai-agents]`; keep those declarations in application code and do not
replace the application's Agent framework. If the developer asked only to run an evaluation,
report the missing harness as a blocker instead of inventing an unrelated
application architecture.

Use the harness's runtime context for process-lifetime telemetry, providers,
and shared clients. Keep mutable state and cleanup invocation-scoped. Register
only useful application-owned target boundaries plus strict, versioned
evaluator expectations. Treat an optional external-Agent target as conceptual
kind `agent`; its exact OpenTelemetry span identifies evidence without turning
it into a native Junjo Agent.

## 2. Translate intent into a dataset

Inspect existing Studio datasets before creating one. Reuse a matching draft
when its intent and cases are correct. Reuse a matching locked dataset for a
new run. Create a clearly versioned dataset when membership or evaluation
meaning must change; never mutate a locked dataset or duplicate it by accident.

Choose targets because they expose behavior relevant to the objective:

- Use a Node for focused prompt or transformation behavior.
- Use a Workflow or subflow for stateful end-to-end behavior.
- Use an Agent for model decisions, Tool use, and downstream effects.

Do not include every declared target automatically. Include multiple scopes
when their comparison materially helps explain upstream and downstream impact.

Author representative scenarios from the product objective, application
behavior, and discovered schemas. Do not impose an arbitrary case count. Cover
the meaningful behavioral variations without redundant cases.

For every case:

- describe the scenario in `case_key`; keep target scope as separate metadata;
- build input JSON that validates against the selected target schema;
- build expectation JSON that validates against the evaluator schema;
- treat an LLM-judge expectation as a binary decision rubric, not an expected
  prose answer;
- make pass conditions observable and reject behavior explicit; and
- keep mechanical JSON in a temporary directory unless it is genuinely
  application-owned source material.

Design each evaluator around one understandable product claim. State binary
pass and fail conditions in terms of evidence the evaluator can actually
observe. Use deterministic checks for deterministic facts and for current
facts that can be verified from a trustworthy current source; do not ask an
LLM judge to supply unstable facts from memory.

Before trusting an evaluator, calibrate it against known-good, known-bad, and
boundary examples. The evaluator owns the binary decision and a concise reason
that names the decision-relevant observation. It does not own full root-cause
analysis; the coding agent uses execution evidence and source code for that.

Use `dataset add` for authored cases. Use `case generate` only when executing
the real target is itself part of dataset authorship. Generated output remains
evidence and must never be silently promoted to the expectation.

Review the complete case set for schema validity, coverage, names, evaluation
meaning, and duplication before irreversibly locking it.

## 3. Execute and retain provenance

Run generation and locked datasets only from a clean committed application
revision. If the tree is dirty, do not hide it, discard work, or commit without
authorization. Report the concrete blocker and continue any safe read-only or
dataset-authoring work that does not misstate source provenance.

Create a stable request key for the exact intent and source revision, choose a
clear human run label, and execute the locked dataset. Parse each versioned JSON
envelope and retain dataset, case, run, Attempt, and execution identities inside
the task; never ask the developer to relay them.

Resume an interrupted Run by its ID. Do not create a replacement for the same
request. Treat these outcomes correctly:

- exit `6`: execution completed with a failed judgment; analyze it as product
  evidence;
- exit `7`: trace evidence is still being ingested or indexed; retry the
  evidence query rather than declaring the evaluation broken; and
- subject, authentication, contract, or Studio failures: preserve the typed
  error and diagnose the actual boundary.

Use current CLI help for all other status and argument details.

## 4. Analyze outcomes and evidence

Retrieve the completed Run and bounded Attempt summaries first. Confirm each
Attempt binds the intended Node, Workflow, or Agent execution and the
application's truthful service identity. Native Junjo targets bind semantic
execution evidence; external Agent targets bind the exact standard
OpenTelemetry span. Use evidence membership only when a known execution must
be followed upstream or downstream.

Hydrate evidence in stages:

1. inspect manifests for failures, errors, surprising passes, and a useful
   representative sample;
2. request the exact failed or otherwise relevant spans named by each manifest;
   and
3. request full evidence only when selected spans cannot resolve a relationship
   or state question, or when the task explicitly requires a complete integrity
   audit.

Do not fetch full evidence for every Attempt by default. Use `junjo eval
explain` and command help for the exact evidence commands and response
contracts.

Explain failures from both the evaluator reason and trace evidence. Locate the
first meaningful behavioral difference rather than blaming the last visible
span. Distinguish a failed quality judgment from target execution, evaluator,
telemetry, authentication, and contract errors.

Lead the report with product meaning:

- what behavior and scenarios were evaluated;
- what passed, failed, or errored and why;
- what the execution evidence shows;
- which evidence remains pending; and
- the smallest justified improvement, if one is evident.

Then include reproducibility metadata: harness and target identities, dataset
and case count, source commit, Run ID and label, comparison transitions when
applicable, and exact Studio resources to inspect.

## 5. Iterate without moving the goalposts

For an authorized improvement request, reuse the same locked dataset. Inspect
the baseline failures and traces, make the smallest application-owned change,
validate it, and commit it before candidate execution when commit authority was
given. Do not change the evaluator or cases merely to make the candidate pass.

Execute the candidate with a new request key and descriptive label. Compare the
complete Dataset unless the developer specifically wants one target scope.
Report improvements, regressions, unchanged outcomes, errors, coverage, and the
first meaningful trace differences.

## Stop only for real blockers

Request developer action only when continuing requires it, including:

- missing Studio, telemetry, or provider credentials;
- a missing harness when implementation was not requested;
- materially ambiguous product intent;
- a dirty worktree that prevents truthful execution; or
- missing authority to modify or commit application code for a candidate.

Do not stop for choices the discovered contracts and product objective let you
make responsibly.

## Example developer requests

- “Use Junjo to baseline whether our assistant recommends authentic local
  places. Store it in Studio and show me the failures. Do not change the app.”
- “Evaluate whether this workflow extracts complete invoice data and explain
  the failures from its traces.”
- “Improve refund-answer accuracy using our existing Junjo dataset, then
  compare the candidate with the baseline.”

# ADR 0010: Node Evaluation Execution

- Status: Accepted
- Date: 2026-07-14
- Owners: Junjo Python SDK

## Context

Application evals need to iterate quickly on one probabilistic Workflow Node.
Calling `Node.service()` directly bypasses Junjo's execution identity, Node and
Store lifecycle, OpenTelemetry spans, and execution correlation. Requiring an
application to reproduce Junjo's private lifecycle would create a second,
unreliable execution path.

Junjo must not become an eval framework. Datasets, rubrics, judges, thresholds,
reports, experiments, and promotion policy belong to the application or a later
evidence-plane capability.

## Decision

The Python SDK provides `evaluate_node()` as a deliberately one-shot execution
envelope. It wraps the supplied real Node and initialized Store in a generated
single-Node Workflow, executes that Workflow through the normal public runtime,
and returns a detached `NodeEvaluationResult` containing:

- the evaluation Workflow run ID;
- the Node definition ID;
- the detached resulting state.

The generated Workflow envelope is truthful evidence and is not hidden. Studio
therefore shows the eval execution as a one-Node Graph with the same Node and
Store telemetry emitted during production Workflow execution. Optional
`ExecutionCorrelation` lets an application attach its trusted eval-case
identity.

The supplied Node and Store are consumed once. Applications construct fresh
instances per case, just as production Workflow factories construct fresh
runtime objects per execution.

## Boundaries

`evaluate_node()` does not:

- call `Node.service()` directly;
- expose or duplicate private lifecycle machinery;
- own provider clients or prompts;
- define eval cases, judges, rubrics, scoring, reports, or persistence;
- claim that a passing deterministic test proves model quality.

Workflow evals continue to call `Workflow.execute()`. Agent evals continue to
call `Agent.execute()`.

## Consequences

- Node evals retain production-equivalent Node/Store lifecycle and telemetry.
- The extra evaluation Workflow span is intentional and visible.
- Applications can link judge results to an exact Studio run without coupling
  eval code to Junjo internals.
- Junjo's public API grows by one small execution helper and one result type.

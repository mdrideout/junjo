# ADR 0010: Node Evaluation Execution

- Status: Accepted
- Date: 2026-07-14
- Owners: Junjo Python SDK
- Amended: 2026-07-27 by ADR 0013 to distinguish this narrow execution helper
  from Junjo's higher-level Studio evaluation framework.

## Context

Application evals need to iterate quickly on one probabilistic Workflow Node.
Calling `Node.service()` directly bypasses Junjo's execution identity, Node and
Store lifecycle, OpenTelemetry spans, and execution correlation. Requiring an
application to reproduce Junjo's private lifecycle would create a second,
unreliable execution path.

At the time this decision was accepted, the intentionally narrow scope was
described as "Junjo must not become an eval framework." That sentence protected
the runtime from absorbing application policy, but it did not settle ownership
of a later Studio-connected evaluation product. ADR 0013 now makes that
ownership explicit.

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

## 2026-07-27 amendment

The `evaluate_node()` decision and its one-shot execution semantics remain
unchanged. It is a low-level public execution primitive used by the
SDK-owned evaluation framework accepted in ADR 0013.

Junjo may own the reusable evaluation harness, Studio client and DTOs, target
and evaluator framework, runner, evaluation context, and CLI without moving
application behavior into the runtime. The application continues to supply:

- typed target declarations and input contracts;
- real dependency and subject construction;
- evaluator-facing output projection; and
- domain-specific evaluator meaning.

This amendment does not make `evaluate_node()` responsible for datasets,
judges, reports, persistence, or Studio transport. Those concerns compose
around it at the higher framework layer.

## Consequences

- Node evals retain production-equivalent Node/Store lifecycle and telemetry.
- The extra evaluation Workflow span is intentional and visible.
- Applications can link judge results to an exact Studio run without coupling
  eval code to Junjo internals.
- Junjo's public API grows by one small execution helper and one result type.
- The higher-level SDK evaluation framework can reuse this faithful execution
  path without duplicating private Node lifecycle behavior.

## Related decisions

- [ADR 0013: SDK-orchestrated, application-executed Studio evaluations](0013-application-executed-studio-evaluations.md)

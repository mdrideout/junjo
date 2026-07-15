# ADR 0011: Workflow execution failure identity

- Status: Accepted
- Date: 2026-07-15
- Owners: Junjo platform

## Context

`Workflow.execute()` returns an `ExecutionResult` containing the run ID after a
successful execution. An admitted execution that failed instead re-raised its
raw inner exception. Hooks and telemetry knew the Workflow run ID, but ordinary
application code at the execution boundary did not. Persisting a failed
application action therefore required an observer side channel or a later
telemetry query.

Agent failures already retain their admitted run identity in typed public
errors. Workflow and Agent composition needs the same property without
flattening the domain or provider failure that explains what went wrong.

Cancellation must remain cancellation. Enriching its identity cannot convert
it into an ordinary failure or weaken propagation through nested executables.

## Decision

### Admitted Workflow failures have a typed boundary error

An execution that reaches Junjo's run-local Workflow context and then fails
raises `WorkflowExecutionError` after terminal Store evidence and lifecycle
delivery have been drained.

Admission begins only after the Graph and Store factories, Graph validation,
compilation, serialization, and complete run-local identity package are
prepared and the Workflow owner span is entered. Initial Store evidence and
lifecycle delivery occur inside that admitted boundary. Failures before it retain
their existing configuration, Graph, serialization, or Store errors because
no execution identity has been published.

The error contains:

- the Workflow or Subflow `run_id`;
- its definition ID and configured name;
- the detached terminal state snapshot; and
- immutable current-scope execution counts.

`state_is_terminal` is true when terminal Store evidence collection completed.
If that terminal machinery fails, the boundary still returns the admitted run
identity, but `state` is explicitly the last detached snapshot available,
`state_is_terminal` is false, and `terminalization_error` retains the separate
machinery failure. The selected body failure or cancellation remains the
exception cause; a terminalization failure after an otherwise successful body
becomes the selected failure cause. Junjo never labels a recovery snapshot as
terminal evidence.

The actual Node, Subflow, Agent, condition, Store, or application exception is
retained as `WorkflowExecutionError.__cause__`. Junjo does not copy its text
into a new domain classification or discard the typed cause. Nested boundaries
therefore form an inspectable cause chain: for example,
`AgentToolError -> WorkflowExecutionError -> domain failure` or
`WorkflowExecutionError -> AgentExecutionError`.

The Workflow failed Hook continues to receive the actual inner execution
failure. Hook events already contain Workflow identity. The typed wrapper is a
caller boundary contract and is not recorded as a second execution failure in
telemetry.

Graph/store factory failures and graph validation or compilation failures that
occur before the run-local context is admitted remain their existing typed
configuration or graph errors. Junjo must not invent a run ID for work that was
never admitted.

### Admitted cancellation remains asyncio cancellation

An admitted Workflow boundary raises `WorkflowCancelledError`, a subclass of
`asyncio.CancelledError`, after owned terminal work is drained. It contains the
same Workflow identity and detached terminal evidence as the failure wrapper,
preserves the cancellation arguments, and retains the original cancellation as
its cause.

This also applies when cancellation reaches the caller during terminal observer
delivery. Such delivery cancellation does not rewrite the already committed
Workflow outcome in telemetry or Hooks. The exception identifies the Workflow
boundary through which cancellation propagated; callers must not infer the
telemetry outcome solely from the exception class.

Every cancellation-aware boundary continues to catch
`asyncio.CancelledError`, cancel active owned work, begin no new work, and
re-raise cancellation. No cancellation becomes `WorkflowExecutionError`.

### Application persistence stores execution identity directly

Applications persist a failed or cancelled Workflow run ID from the typed
boundary error. They do not install Hooks as a control plane and do not scrape
telemetry to discover the ID.

If a process stops before terminal reconciliation executes, a durable
application store may have active application actions without a known Workflow
run ID. Startup recovery must preserve any identity already committed, record
an explicit interruption reason, and make those actions terminal in one
storage transaction so they cannot block future work forever.

## Consequences

- Success, admitted failure, and admitted cancellation all expose the same
  trustworthy Workflow run identity at the direct call boundary.
- Existing callers that caught an inner admitted Workflow exception directly
  must catch `WorkflowExecutionError` and inspect `__cause__`.
- Callers that require a complete terminal snapshot must check
  `state_is_terminal`; a false value remains diagnostic evidence, not a
  completed Store transaction.
- Cancellation callers can continue catching `asyncio.CancelledError`.
- Telemetry schemas do not change. Existing spans and lifecycle events already
  carry this identity and continue to describe the inner failure.
- Applications can durably connect failed product actions to Studio without an
  observer side channel.

## Rejected alternatives

- Mutating arbitrary inner exceptions with a `run_id`: exception classes are
  application-owned and provide no trustworthy Junjo boundary contract.
- Returning an output-less `ExecutionResult`: failure is not success.
- Reading the run ID from a Hook: Hooks are optional observers, not execution
  control flow.
- Querying telemetry after failure: export is asynchronous and may be
  unavailable precisely when the application needs to persist its action.
- Converting cancellation to an ordinary Workflow error: this breaks asyncio
  cancellation semantics.

## Related decisions

- [ADR 0003: Agent execution model](0003-agent-execution-model.md)
- [ADR 0005: Agent and Workflow composition](0005-agent-workflow-composition.md)
- [ADR 0007: Execution correlation and Studio resolution](0007-execution-correlation-and-studio-resolution.md)
- [ADR 0008: Versioned application object persistence](0008-versioned-application-object-persistence.md)

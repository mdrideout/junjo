import { describe, expect, it } from 'vitest'
import {
  AgentExecutionDetailSchema,
  AgentOperationSchema,
  CandidateEvidenceSchema,
  PayloadEvidenceSchema,
  RequestedToolCallSchema,
} from './agent-execution'
import { makeAgentExecutionDetailFixture } from '../testing/fixtures'

describe('Agent execution semantic schemas', () => {
  it('parses a complete backend-owned semantic projection', () => {
    const detail = AgentExecutionDetailSchema.parse(makeAgentExecutionDetailFixture())

    expect(detail.summary.agent_key).toBe('chat-agent')
    expect(detail.operations).toHaveLength(2)
    expect(detail.operations[0]?.operation_type).toBe('model_request')
  })

  it('rejects unknown fields and non-canonical identities at the API boundary', () => {
    const extraField = { ...makeAgentExecutionDetailFixture(), transport_spans: [] }
    expect(AgentExecutionDetailSchema.safeParse(extraField).success).toBe(false)

    const invalidIdentity = makeAgentExecutionDetailFixture()
    invalidIdentity.summary.trace_id = 'AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA'
    expect(AgentExecutionDetailSchema.safeParse(invalidIdentity).success).toBe(false)
  })

  it.each([
    {
      mode: 'full',
      policy: 'full',
      value: { visible: true },
      reference: null,
      reason: null,
    },
    {
      mode: 'redacted',
      policy: 'redacted',
      value: { secret: '[REDACTED]' },
      reference: null,
      reason: null,
    },
    {
      mode: 'excluded',
      policy: 'excluded',
      value: null,
      reference: null,
      reason: null,
    },
    {
      mode: 'reference',
      policy: 'reference',
      value: null,
      reference: 's3://diagnostics/evidence.json',
      reason: null,
    },
    {
      mode: 'missing',
      policy: null,
      value: null,
      reference: null,
      reason: 'Required event was not preserved.',
    },
  ])('parses explicit $mode payload evidence', (evidence) => {
    expect(PayloadEvidenceSchema.parse(evidence)).toEqual(evidence)
  })

  it('does not conflate an excluded payload with missing forensic evidence', () => {
    expect(
      PayloadEvidenceSchema.safeParse({
        mode: 'excluded',
        policy: 'excluded',
        value: null,
        reference: null,
        reason: 'not allowed for excluded evidence',
      }).success,
    ).toBe(false)

    expect(
      PayloadEvidenceSchema.safeParse({
        mode: 'missing',
        policy: 'excluded',
        value: null,
        reference: null,
        reason: 'Missing evidence cannot claim a producer policy.',
      }).success,
    ).toBe(false)
  })

  it('rejects normalized JSON outside the shared I-JSON domain', () => {
    expect(
      PayloadEvidenceSchema.safeParse({
        mode: 'full',
        policy: 'full',
        value: { unsafe: Number.MAX_SAFE_INTEGER + 1 },
        reference: null,
        reason: null,
      }).success,
    ).toBe(false)

    expect(
      PayloadEvidenceSchema.safeParse({
        mode: 'full',
        policy: 'full',
        value: { invalidUnicode: '\ud800' },
        reference: null,
        reason: null,
      }).success,
    ).toBe(false)
  })

  it('enforces candidate availability as an explicit evidence state', () => {
    expect(
      CandidateEvidenceSchema.safeParse({
        available: true,
        payload: null,
        unavailable_reason: null,
      }).success,
    ).toBe(false)

    expect(
      CandidateEvidenceSchema.safeParse({
        available: false,
        payload: null,
        unavailable_reason: 'service_failed',
      }).success,
    ).toBe(true)

    expect(
      CandidateEvidenceSchema.safeParse({
        available: false,
        payload: null,
        unavailable_reason: 'arbitrary reason',
      }).success,
    ).toBe(false)
  })

  it('accepts partial projections with sequence gaps and unavailable Store snapshots', () => {
    const partial = makeAgentExecutionDetailFixture()
    partial.operations[1]!.sequence = 4
    partial.state.reconstructable = false
    partial.state.reconstruction_status = 'failed'
    partial.state.reconstruction_reason = 'operation_sequence_gap'
    partial.state.transitions[0]!.before = null
    partial.state.transitions[0]!.after = null
    partial.integrity = {
      status: 'partial',
      diagnostics: [
        {
          code: 'operation_sequence_gap',
          path: 'operations[1].sequence',
          message: 'Expected sequence 2 but observed sequence 4.',
        },
      ],
      loss_counts: {
        ...partial.integrity.loss_counts,
        span_dropped_events: 2,
      },
    }

    expect(AgentExecutionDetailSchema.parse(partial).integrity.status).toBe('partial')
  })

  it('requires requested Tool diagnostics to remain model-owned and strict', () => {
    expect(
      RequestedToolCallSchema.parse({
        call_id: 'call-unknown',
        ordinal: 2,
        tool_name: 'delete_everything',
        observed_tool_operation: false,
        admission: 'not_admitted',
        reason: 'unknown_tool',
      }),
    ).toMatchObject({ admission: 'not_admitted', observed_tool_operation: false })

    expect(
      RequestedToolCallSchema.safeParse({
        call_id: 'call-unknown',
        ordinal: 2,
        tool_name: 'delete_everything',
        observed_tool_operation: false,
        admission: 'not_admitted',
        reason: 'unknown_tool',
        operation_sequence: 3,
      }).success,
    ).toBe(false)

    expect(
      RequestedToolCallSchema.parse({
        call_id: 'call-admitted',
        ordinal: 3,
        tool_name: 'lookup',
        observed_tool_operation: false,
        admission: 'admitted',
        reason: 'execution_interrupted',
      }),
    ).toMatchObject({ admission: 'admitted', observed_tool_operation: false })

    expect(
      RequestedToolCallSchema.parse({
        call_id: 'call-opaque',
        ordinal: 4,
        tool_name: 'lookup',
        observed_tool_operation: true,
        admission: 'unknown',
        reason: 'store_evidence_unavailable',
      }),
    ).toMatchObject({ admission: 'unknown', observed_tool_operation: true })
  })

  it('rejects cross-field contradictions in outcome, operations, and integrity', () => {
    const outcomeMismatch = makeAgentExecutionDetailFixture()
    outcomeMismatch.summary.outcome = 'failed'
    expect(AgentExecutionDetailSchema.safeParse(outcomeMismatch).success).toBe(false)

    const admittedWithoutOperation = makeAgentExecutionDetailFixture()
    const modelOperation = admittedWithoutOperation.operations[0]
    if (modelOperation?.operation_type !== 'model_request') throw new Error('Fixture model operation missing')
    modelOperation.requested_tool_calls[0]!.observed_tool_operation = false
    expect(AgentExecutionDetailSchema.safeParse(admittedWithoutOperation).success).toBe(false)

    const incompleteToolSuccess = makeAgentExecutionDetailFixture()
    const toolOperation = incompleteToolSuccess.operations[1]
    if (toolOperation?.operation_type !== 'tool') throw new Error('Fixture Tool operation missing')
    toolOperation.result = null
    expect(AgentExecutionDetailSchema.safeParse(incompleteToolSuccess).success).toBe(false)

    const hiddenLoss = makeAgentExecutionDetailFixture()
    hiddenLoss.integrity.loss_counts.span_dropped_events = 1
    expect(AgentExecutionDetailSchema.safeParse(hiddenLoss).success).toBe(false)
  })

  it('mirrors every backend Model operation evidence invariant', () => {
    const fixture = makeAgentExecutionDetailFixture()
    const original = fixture.operations[0]
    if (original?.operation_type !== 'model_request') throw new Error('Fixture model operation missing')

    const completedWithoutResponse = structuredClone(original)
    completedWithoutResponse.response_type = null
    completedWithoutResponse.response = null
    completedWithoutResponse.usage = null
    completedWithoutResponse.requested_tool_calls = []
    expect(AgentOperationSchema.safeParse(completedWithoutResponse).success).toBe(false)

    const failedWithResponse = structuredClone(original)
    failedWithResponse.outcome = 'failed'
    failedWithResponse.error = { type: 'ModelError', message: null, stacktrace: null }
    failedWithResponse.usage = null
    expect(AgentOperationSchema.safeParse(failedWithResponse).success).toBe(false)

    const cancelledWithUsage = structuredClone(original)
    cancelledWithUsage.outcome = 'cancelled'
    cancelledWithUsage.cancellation = { reason: 'caller cancelled' }
    cancelledWithUsage.response_type = null
    cancelledWithUsage.response = null
    cancelledWithUsage.requested_tool_calls = []
    expect(AgentOperationSchema.safeParse(cancelledWithUsage).success).toBe(false)
  })

  it('mirrors every backend Tool operation result and revision invariant', () => {
    const fixture = makeAgentExecutionDetailFixture()
    const original = fixture.operations[1]
    if (original?.operation_type !== 'tool') throw new Error('Fixture Tool operation missing')

    for (const outcome of ['failed', 'cancelled'] as const) {
      const nonCompletedWithCommit = structuredClone(original)
      nonCompletedWithCommit.outcome = outcome
      nonCompletedWithCommit.error = outcome === 'failed'
        ? { type: 'ToolError', message: null, stacktrace: null }
        : null
      nonCompletedWithCommit.cancellation = outcome === 'cancelled'
        ? { reason: 'caller cancelled' }
        : null
      expect(AgentOperationSchema.safeParse(nonCompletedWithCommit).success).toBe(false)
    }

    const resultWithoutRevision = structuredClone(original)
    resultWithoutRevision.state_revision_after = null
    expect(AgentOperationSchema.safeParse(resultWithoutRevision).success).toBe(false)

    const revisionWithoutResult = structuredClone(original)
    revisionWithoutResult.result = null
    expect(AgentOperationSchema.safeParse(revisionWithoutResult).success).toBe(false)
  })

  it('rejects unavailable or verified Store claims without the required evidence', () => {
    const unavailableWithEvidence = makeAgentExecutionDetailFixture()
    unavailableWithEvidence.state.available = false
    expect(AgentExecutionDetailSchema.safeParse(unavailableWithEvidence).success).toBe(false)

    const verifiedWithoutEnd = makeAgentExecutionDetailFixture()
    verifiedWithoutEnd.state.end = null
    expect(AgentExecutionDetailSchema.safeParse(verifiedWithoutEnd).success).toBe(false)
  })
})

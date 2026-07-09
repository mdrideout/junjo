import { describe, expect, it } from 'vitest'
import { loadJunjoTransportFixtureCase } from '../../../test-utils/junjo-fixture-loader'
import { OtelSpan, OtelSpanSchema } from '../schemas/schemas'
import { wrapSpan } from './span-accessor'

function loadFixtureSpans(caseName: string): OtelSpan[] {
  const fixture = loadJunjoTransportFixtureCase(caseName)
  return OtelSpanSchema.array().parse(fixture.spans)
}

function findSpan(spans: OtelSpan[], spanId: string): OtelSpan {
  const span = spans.find((candidate) => candidate.span_id === spanId)
  if (!span) {
    throw new Error(`Expected span ${spanId} in fixture`)
  }

  return span
}

describe('SpanAccessor', () => {
  it('parses current workflow executable fields and execution graph snapshots', () => {
    const spans = loadFixtureSpans('basic_workflow_success')
    const workflow = wrapSpan(findSpan(spans, '1111111111111111'))

    expect(workflow.isWorkflow).toBe(true)
    expect(workflow.executableDefinitionId).toBe('workflow.basic')
    expect(workflow.executableRuntimeId).toBe('run-basic-01')
    expect(workflow.executableStructuralId).toBe('graph-basic-01')
    expect(workflow.workflowStoreId).toBe('store-basic-01')
    expect(workflow.workflowStateStart).toEqual({ input: 'hello', output: null })
    expect(workflow.workflowExecutionGraphSnapshot?.graphStructuralId).toBe('graph-basic-01')
    expect(workflow.workflowExecutionGraphSnapshot?.nodes.map((node) => node.nodeRuntimeId)).toEqual([
      'node.basic.fetch_input',
      'node.basic.transform_output',
    ])
    expect(workflow.hasFailureSignal).toBe(false)
  })

  it('maps subflows to definition-backed graph node IDs and preserves parent store metadata', () => {
    const spans = loadFixtureSpans('subflow_with_parent_store')
    const subflow = wrapSpan(findSpan(spans, '2222222222222223'))

    expect(subflow.isSubflow).toBe(true)
    expect(subflow.workflowStoreId).toBe('store-subflow-child-01')
    expect(subflow.workflowParentStoreId).toBe('store-subflow-parent-01')
    expect(subflow.workflowExecutionGraphSnapshot?.graphStructuralId).toBe('graph-child-subflow-01')
  })

  it('maps run_concurrent spans to runtime-backed graph node IDs', () => {
    const spans = loadFixtureSpans('run_concurrent_success')
    const runConcurrent = wrapSpan(findSpan(spans, '3333333333333333'))

    expect(runConcurrent.isRunConcurrent).toBe(true)
    expect(runConcurrent.hasFailureSignal).toBe(false)
  })

  it('treats exception spans and hook error spans as failures', () => {
    const failedSpans = loadFixtureSpans('failed_executable_with_error_type')
    const failedSpan = wrapSpan(findSpan(failedSpans, '4444444444444443'))

    expect(failedSpan.errorType).toBe('ValueError')
    expect(failedSpan.exceptionEvents).toHaveLength(1)
    expect(failedSpan.hasFailureSignal).toBe(true)

    const hookFailureSpans = loadFixtureSpans('hook_failure_on_surrounding_span')
    const hookFailureSpan = wrapSpan(findSpan(hookFailureSpans, '6666666666666662'))

    expect(hookFailureSpan.hookErrorEvents).toHaveLength(1)
    expect(hookFailureSpan.hookErrorEvents[0].attributes['junjo.hook.error.message']).toBe('hook exploded')
    expect(hookFailureSpan.hasFailureSignal).toBe(true)
  })

  it('does not treat cancelled spans as failures', () => {
    const spans = loadFixtureSpans('cancelled_executable')
    const cancelledSpan = wrapSpan(findSpan(spans, '5555555555555552'))

    expect(cancelledSpan.isCancelled).toBe(true)
    expect(cancelledSpan.cancelledReason).toBe('sibling_failed')
    expect(cancelledSpan.hasFailureSignal).toBe(false)
  })
})

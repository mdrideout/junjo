import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'
import { loadJunjoTransportFixtureCase } from '../test-utils/junjo-fixture-loader'
import { OtelSpan, OtelSpanSchema } from '../features/traces/schemas/schemas'
import { JGraph, JGraphSchema } from '../junjo-graph/schemas'
import {
  findRenderedGraphNodeIdForSpan,
  findNearestSpanRepresentedInGraph,
  findSpanForRenderedGraphNodeId,
} from './junjo-graph-span-matching'

const telemetryFixtures = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  '../../../../../contracts/telemetry/fixtures',
)

function loadFixtureSpans(caseName: string): OtelSpan[] {
  const fixture = loadJunjoTransportFixtureCase(caseName)
  return OtelSpanSchema.array().parse(fixture.spans)
}

function loadWorkflowGraph(spans: OtelSpan[], workflowSpanId: string): JGraph {
  const workflowSpan = spans.find((span) => span.span_id === workflowSpanId)
  if (!workflowSpan) {
    throw new Error(`Expected workflow span ${workflowSpanId}`)
  }

  const rawSnapshot = workflowSpan.attributes_json['junjo.workflow.execution_graph_snapshot']
  if (typeof rawSnapshot !== 'string') {
    throw new Error(`Expected execution graph snapshot string for ${workflowSpanId}`)
  }

  return JGraphSchema.parse(JSON.parse(rawSnapshot))
}

function findSpan(spans: OtelSpan[], spanId: string): OtelSpan {
  const span = spans.find((candidate) => candidate.span_id === spanId)
  if (!span) {
    throw new Error(`Expected span ${spanId}`)
  }

  return span
}

describe('Junjo graph span matching', () => {
  it('matches normal graph nodes to node spans by executable runtime id', () => {
    const spans = loadFixtureSpans('basic_workflow_success')
    const graph = loadWorkflowGraph(spans, '1111111111111111')

    const span = findSpanForRenderedGraphNodeId(graph, 'node.basic.fetch_input', spans)

    expect(span?.span_id).toBe('1111111111111112')
  })

  it('matches run_concurrent nodes to concurrent spans by executable runtime id', () => {
    const spans = loadFixtureSpans('run_concurrent_success')
    const graph = loadWorkflowGraph(spans, '3333333333333331')
    const concurrentSpan = findSpan(spans, '3333333333333333')

    expect(findSpanForRenderedGraphNodeId(graph, 'run.concurrent.fanout', spans)?.span_id).toBe(
      '3333333333333333',
    )
    expect(findRenderedGraphNodeIdForSpan(graph, concurrentSpan)).toBe('run.concurrent.fanout')
  })

  it('matches parent-graph subflow container nodes to subflow spans by structural identity', () => {
    const spans = loadFixtureSpans('subflow_with_parent_store')
    const graph = loadWorkflowGraph(spans, '2222222222222221')
    const subflowSpan = findSpan(spans, '2222222222222223')

    expect(findSpanForRenderedGraphNodeId(graph, 'node.subflow.container', spans)?.span_id).toBe(
      '2222222222222223',
    )
    expect(findRenderedGraphNodeIdForSpan(graph, subflowSpan)).toBe('node.subflow.container')
  })

  it('maps Agent and model descendants to the nearest Node represented in the Workflow Graph', () => {
    const fixture = JSON.parse(fs.readFileSync(
      path.join(telemetryFixtures, 'agent/producer/agent_inside_workflow_node.json'),
      'utf8',
    )) as { spans: unknown[] }
    const spans = OtelSpanSchema.array().parse(fixture.spans)
    const graph = loadWorkflowGraph(spans, 'd838aca111e3a971')
    const agentSpan = findSpan(spans, '98d460d32e3bcb3e')
    const modelSpan = findSpan(spans, '2c1f5a649f51c1b3')

    expect(findNearestSpanRepresentedInGraph(graph, agentSpan, spans)?.span_id)
      .toBe('d528888d4b23da30')
    expect(findNearestSpanRepresentedInGraph(graph, modelSpan, spans)?.span_id)
      .toBe('d528888d4b23da30')
  })
})

import { describe, expect, it } from 'vitest'
import { loadJunjoTransportFixtureCase } from '../test-utils/junjo-fixture-loader'
import { OtelSpanSchema } from '../features/traces/schemas/schemas'
import { JunjoGraph } from './junjo-graph'

function loadWorkflowGraph(caseName: string, workflowSpanId: string) {
  const fixture = loadJunjoTransportFixtureCase(caseName)
  const spans = OtelSpanSchema.array().parse(fixture.spans)
  const workflowSpan = spans.find((span) => span.span_id === workflowSpanId)

  if (!workflowSpan) {
    throw new Error(`Expected workflow span ${workflowSpanId} in fixture`)
  }

  const rawSnapshot = workflowSpan.attributes_json['junjo.workflow.execution_graph_snapshot']
  if (typeof rawSnapshot !== 'string') {
    throw new Error(`Expected string execution graph snapshot for ${caseName}`)
  }

  return JunjoGraph.fromJson(JSON.parse(rawSnapshot))
}

describe('JunjoGraph', () => {
  it('renders current workflow execution snapshots into Mermaid nodes and edges', () => {
    const graph = loadWorkflowGraph('basic_workflow_success', '1111111111111111')
    const mermaid = graph.toMermaid()

    expect(mermaid).toContain('graph LR')
    expect(mermaid).toContain('node.basic.fetch_input@{ shape: rect, label: "fetch_input" }')
    expect(mermaid).toContain('node.basic.fetch_input --> node.basic.transform_output')
  })

  it('renders run_concurrent snapshots as Mermaid subgraphs', () => {
    const graph = loadWorkflowGraph('run_concurrent_success', '3333333333333331')
    const mermaid = graph.toMermaid()

    expect(mermaid).toContain('subgraph run.concurrent.fanout ["fanout"]')
    expect(mermaid).toContain('node.concurrent.branch_a@{ shape: rect, label: "branch_a" }')
    expect(mermaid).toContain('node.concurrent.prepare --> run.concurrent.fanout')
  })

  it('omits subflow-scoped internal edges from parent workflow Mermaid output', () => {
    const graph = loadWorkflowGraph('subflow_with_parent_store', '2222222222222221')
    const mermaid = graph.toMermaid()

    expect(mermaid).toContain('node.subflow.container@{ shape: st-rect, label: "child_subflow" }')
    expect(mermaid).toContain('node.subflow.prepare --> node.subflow.container')
    expect(mermaid).not.toContain('node.child.entry --> node.child.exit')
  })
})

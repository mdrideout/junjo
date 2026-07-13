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

  it('omits subflow-internal concurrent clusters and defensive internal endpoint edges', () => {
    const graph = JunjoGraph.fromJson({
      v: 2,
      graphStructuralId: 'graph-parent-with-concurrent-subflow',
      nodes: [
        {
          nodeRuntimeId: 'parent.prepare',
          nodeStructuralId: 'struct-parent-prepare',
          nodeType: 'Node',
          nodeLabel: 'prepare',
        },
        {
          nodeRuntimeId: 'parent.subflow',
          nodeStructuralId: 'struct-parent-subflow',
          nodeType: 'Workflow',
          nodeLabel: 'child_subflow',
          isSubflow: true,
          subflowGraphStructuralId: 'graph-child-with-concurrent',
        },
        {
          nodeRuntimeId: 'parent.done',
          nodeStructuralId: 'struct-parent-done',
          nodeType: 'Node',
          nodeLabel: 'done',
        },
        {
          nodeRuntimeId: 'child.concurrent',
          nodeStructuralId: 'struct-child-concurrent',
          nodeType: 'RunConcurrent',
          nodeLabel: 'child fanout',
          isConcurrentSubgraph: true,
          childNodeRuntimeIds: ['child.branch_a', 'child.branch_b'],
        },
        {
          nodeRuntimeId: 'child.branch_a',
          nodeStructuralId: 'struct-child-branch-a',
          nodeType: 'Node',
          nodeLabel: 'branch_a',
        },
        {
          nodeRuntimeId: 'child.branch_b',
          nodeStructuralId: 'struct-child-branch-b',
          nodeType: 'Node',
          nodeLabel: 'branch_b',
        },
        {
          nodeRuntimeId: 'child.done',
          nodeStructuralId: 'struct-child-done',
          nodeType: 'Node',
          nodeLabel: 'child_done',
        },
      ],
      edges: [
        {
          edgeStructuralId: 'edge-parent-prepare-subflow',
          tailNodeRuntimeId: 'parent.prepare',
          tailNodeStructuralId: 'struct-parent-prepare',
          headNodeRuntimeId: 'parent.subflow',
          headNodeStructuralId: 'struct-parent-subflow',
          edgeConditionLabel: null,
          edgeScope: 'explicit',
          parentSubflowRuntimeId: null,
        },
        {
          edgeStructuralId: 'edge-parent-subflow-done',
          tailNodeRuntimeId: 'parent.subflow',
          tailNodeStructuralId: 'struct-parent-subflow',
          headNodeRuntimeId: 'parent.done',
          headNodeStructuralId: 'struct-parent-done',
          edgeConditionLabel: null,
          edgeScope: 'explicit',
          parentSubflowRuntimeId: null,
        },
        {
          edgeStructuralId: 'edge-child-concurrent-done',
          tailNodeRuntimeId: 'child.concurrent',
          tailNodeStructuralId: 'struct-child-concurrent',
          headNodeRuntimeId: 'child.done',
          headNodeStructuralId: 'struct-child-done',
          edgeConditionLabel: null,
          edgeScope: 'subflow',
          parentSubflowRuntimeId: 'parent.subflow',
        },
        {
          edgeStructuralId: 'edge-defensive-parent-internal',
          tailNodeRuntimeId: 'parent.prepare',
          tailNodeStructuralId: 'struct-parent-prepare',
          headNodeRuntimeId: 'child.concurrent',
          headNodeStructuralId: 'struct-child-concurrent',
          edgeConditionLabel: null,
          edgeScope: 'explicit',
          parentSubflowRuntimeId: null,
        },
      ],
    })

    const mermaid = graph.toMermaid()

    expect(mermaid).toContain('parent.prepare@{ shape: rect, label: "prepare" }')
    expect(mermaid).toContain('parent.subflow@{ shape: st-rect, label: "child_subflow" }')
    expect(mermaid).toContain('parent.subflow --> parent.done')
    expect(mermaid).not.toContain('subgraph child.concurrent')
    expect(mermaid).not.toContain('child.branch_a')
    expect(mermaid).not.toContain('child.branch_b')
    expect(mermaid).not.toContain('parent.prepare --> child.concurrent')
    expect(mermaid).not.toContain('child.concurrent --> child.done')
  })

  it('omits no-edge single-node subflow internals from parent workflow Mermaid output', () => {
    const graph = JunjoGraph.fromJson({
      v: 2,
      graphStructuralId: 'graph-parent-with-single-node-subflow',
      nodes: [
        {
          nodeRuntimeId: 'parent.prepare',
          nodeStructuralId: 'struct-parent-prepare',
          nodeType: 'Node',
          nodeLabel: 'prepare',
        },
        {
          nodeRuntimeId: 'parent.subflow',
          nodeStructuralId: 'struct-parent-subflow',
          nodeType: 'Workflow',
          nodeLabel: 'single_node_subflow',
          isSubflow: true,
          subflowGraphStructuralId: 'graph-child-single-node',
          subflowSourceNodeRuntimeId: 'child.only_node',
          subflowSourceNodeStructuralId: 'struct-child-only',
          subflowSinkNodeRuntimeIds: ['child.only_node'],
          subflowSinkNodeStructuralIds: ['struct-child-only'],
        },
        {
          nodeRuntimeId: 'parent.done',
          nodeStructuralId: 'struct-parent-done',
          nodeType: 'Node',
          nodeLabel: 'done',
        },
        {
          nodeRuntimeId: 'child.only_node',
          nodeStructuralId: 'struct-child-only',
          nodeType: 'Node',
          nodeLabel: 'child_only_node',
        },
      ],
      edges: [
        {
          edgeStructuralId: 'edge-parent-prepare-subflow',
          tailNodeRuntimeId: 'parent.prepare',
          tailNodeStructuralId: 'struct-parent-prepare',
          headNodeRuntimeId: 'parent.subflow',
          headNodeStructuralId: 'struct-parent-subflow',
          edgeConditionLabel: null,
          edgeScope: 'explicit',
          parentSubflowRuntimeId: null,
        },
        {
          edgeStructuralId: 'edge-parent-subflow-done',
          tailNodeRuntimeId: 'parent.subflow',
          tailNodeStructuralId: 'struct-parent-subflow',
          headNodeRuntimeId: 'parent.done',
          headNodeStructuralId: 'struct-parent-done',
          edgeConditionLabel: null,
          edgeScope: 'explicit',
          parentSubflowRuntimeId: null,
        },
      ],
    })

    const mermaid = graph.toMermaid()

    expect(mermaid).toContain('parent.prepare@{ shape: rect, label: "prepare" }')
    expect(mermaid).toContain('parent.subflow@{ shape: st-rect, label: "single_node_subflow" }')
    expect(mermaid).toContain('parent.subflow --> parent.done')
    expect(mermaid).not.toContain('child.only_node')
    expect(mermaid).not.toContain('child_only_node')
  })
})

import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest'
import mermaid from 'mermaid'
import { loadJunjoTransportFixtureCase } from '../test-utils/junjo-fixture-loader'
import { OtelSpanSchema } from '../features/traces/schemas/schemas'
import { JunjoGraph } from '../junjo-graph/junjo-graph'
import { JGraphSchema } from '../junjo-graph/schemas'
import { indexRenderedGraphElements } from './mermaid-dom-adapter'

beforeAll(() => {
  mermaid.initialize({
    startOnLoad: false,
    theme: 'neutral',
    flowchart: { htmlLabels: true, curve: 'linear' },
  })
  Object.defineProperty(SVGElement.prototype, 'getBBox', {
    configurable: true,
    value: vi.fn(() => ({ x: 0, y: 0, width: 100, height: 30 })),
  })
  Object.defineProperty(SVGElement.prototype, 'getComputedTextLength', {
    configurable: true,
    value: vi.fn(() => 80),
  })
})

afterEach(() => {
  document.body.innerHTML = ''
})

async function renderFixtureGraph(caseName: string, workflowSpanId: string) {
  const spans = OtelSpanSchema.array().parse(loadJunjoTransportFixtureCase(caseName).spans)
  const workflowSpan = spans.find((span) => span.span_id === workflowSpanId)
  const snapshotJson = workflowSpan?.attributes_json['junjo.workflow.execution_graph_snapshot']
  if (typeof snapshotJson !== 'string') throw new Error('Workflow Graph snapshot missing')
  const snapshot = JGraphSchema.parse(JSON.parse(snapshotJson))
  const source = JunjoGraph.fromJson(snapshot).toMermaid()
  const rendered = await mermaid.render(`real-renderer-${caseName}`, source)
  const container = document.createElement('div')
  container.innerHTML = rendered.svg
  document.body.append(container)
  return { snapshot, container, index: indexRenderedGraphElements(container, snapshot) }
}

describe('Mermaid DOM adapter with the installed renderer', () => {
  it('indexes ordinary nodes using Junjo-owned identity', async () => {
    const { snapshot, index } = await renderFixtureGraph(
      'basic_workflow_success',
      '1111111111111111',
    )

    expect([...index.keys()].sort()).toEqual(
      snapshot.nodes.map((node) => node.nodeRuntimeId).sort(),
    )
    expect(index.get('node.basic.fetch_input'))
      .toHaveAttribute('data-junjo-graph-node-id', 'node.basic.fetch_input')
  })

  it('indexes RunConcurrent clusters and their child nodes', async () => {
    const { snapshot, index } = await renderFixtureGraph(
      'run_concurrent_success',
      '3333333333333331',
    )

    expect([...index.keys()].sort()).toEqual(
      snapshot.nodes.map((node) => node.nodeRuntimeId).sort(),
    )
    expect(index.get('run.concurrent.fanout')?.classList.contains('cluster')).toBe(true)
  })

  it('indexes a Subflow container without confusing its internal Graph nodes', async () => {
    const { index } = await renderFixtureGraph(
      'subflow_with_parent_store',
      '2222222222222221',
    )

    expect(index.get('node.subflow.container'))
      .toHaveAttribute('data-junjo-graph-node-id', 'node.subflow.container')
  })
})

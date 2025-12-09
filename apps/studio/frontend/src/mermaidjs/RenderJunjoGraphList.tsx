import { identifySpanWorkflowChain } from '../features/traces/store/selectors'
import { JunjoGraph } from '../junjo-graph/junjo-graph'
import { useAppSelector } from '../root-store/hooks'
import { RootState } from '../root-store/store'
import RenderJunjoGraphMermaid from './RenderJunjoGraphMermaid'

interface RenderJunjoGraphListProps {
  traceId: string
  workflowSpanId: string
  showEdgeLabels: boolean
}

/**
 * Check if a graph structure object has the required fields for rendering.
 * Returns true if the structure has v (version), nodes array, and edges array.
 */
function hasValidGraphStructure(graphStructure: Record<string, unknown> | undefined): boolean {
  if (!graphStructure || typeof graphStructure !== 'object') {
    return false
  }
  return (
    typeof graphStructure.v === 'number' &&
    Array.isArray(graphStructure.nodes) &&
    Array.isArray(graphStructure.edges)
  )
}

export default function RenderJunjoGraphList(props: RenderJunjoGraphListProps) {
  const { traceId, workflowSpanId, showEdgeLabels } = props

  const workflowChain = useAppSelector((state: RootState) =>
    identifySpanWorkflowChain(state, {
      traceId,
      workflowSpanId,
    }),
  )

  return workflowChain.map((workflowSpan) => {
    const uniqueMermaidId = `mer-unique-${workflowSpan.span_id}`

    // Check if the workflow has valid graph structure data
    if (!hasValidGraphStructure(workflowSpan.junjo_wf_graph_structure)) {
      return (
        <div key={`key-${uniqueMermaidId}`} className={'mb-5'}>
          <div className={'font-bold text-sm'}>{workflowSpan.name}</div>
          <div className={'text-sm text-gray-500 italic p-4'}>
            Graph structure not available for this workflow.
          </div>
        </div>
      )
    }

    // Parse mermaid flow string
    const mermaidFlowString = JunjoGraph.fromJson(workflowSpan.junjo_wf_graph_structure).toMermaid(
      showEdgeLabels,
    )

    return (
      <div key={`key-${uniqueMermaidId}`} className={'mb-5'}>
        <div className={'font-bold text-sm'}>{workflowSpan.name}</div>
        <RenderJunjoGraphMermaid
          traceId={traceId}
          workflowChain={workflowChain}
          mermaidFlowString={mermaidFlowString}
          mermaidUniqueId={uniqueMermaidId}
          workflowSpanId={workflowSpan.span_id}
        />
      </div>
    )
  })
}

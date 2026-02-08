import { identifySpanWorkflowChain } from '../features/traces/store/selectors'
import { wrapSpan } from '../features/traces/utils/span-accessor'
import { JunjoGraph } from '../junjo-graph/junjo-graph'
import { useAppSelector } from '../root-store/hooks'
import { RootState } from '../root-store/store'
import RenderJunjoGraphMermaid from './RenderJunjoGraphMermaid'

interface RenderJunjoGraphListProps {
  traceId: string
  workflowSpanId: string
  showEdgeLabels: boolean
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
    const accessor = wrapSpan(workflowSpan)
    const graphStructure = accessor.workflowGraphStructure

    // Check if the workflow has valid graph structure data
    if (!graphStructure) {
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
    const mermaidFlowString = JunjoGraph.fromJson(graphStructure).toMermaid(showEdgeLabels)

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

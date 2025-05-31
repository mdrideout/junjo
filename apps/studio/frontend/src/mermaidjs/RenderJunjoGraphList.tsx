import { identifyWorkflowChain } from '../features/otel/store/selectors'
import { JunjoGraph } from '../junjo-graph/junjo-graph'
import { useAppSelector } from '../root-store/hooks'
import { RootState } from '../root-store/store'
import RenderJunjoGraphMermaid from './RenderJunjoGraphMermaid'

interface RenderJunjoGraphListProps {
  serviceName: string
  workflowSpanID: string
  showEdgeLabels: boolean
}

export default function RenderJunjoGraphList(props: RenderJunjoGraphListProps) {
  const { serviceName, workflowSpanID, showEdgeLabels } = props

  const workflowChain = useAppSelector((state: RootState) =>
    identifyWorkflowChain(state, {
      serviceName,
      spanID: workflowSpanID,
    }),
  )

  return workflowChain.map((workflowSpan) => {
    // Parse mermaid flow string
    const mermaidFlowString = JunjoGraph.fromJson(workflowSpan.junjo_wf_graph_structure).toMermaid(
      showEdgeLabels,
    )
    const uniqueMermaidId = `mer-unique-${workflowSpan.span_id}`

    console.log(`Mermaid string ${uniqueMermaidId}:\n`, mermaidFlowString)

    return (
      <div key={`key-${uniqueMermaidId}`} className={'mb-5'}>
        <div className={'font-bold text-sm'}>{workflowSpan.name}</div>
        <RenderJunjoGraphMermaid
          mermaidFlowString={mermaidFlowString}
          mermaidUniqueId={uniqueMermaidId}
          serviceName={serviceName}
          workflowSpanID={workflowSpan.span_id}
        />
      </div>
    )
  })
}

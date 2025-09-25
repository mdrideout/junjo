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

export default function RenderJunjoGraphList(props: RenderJunjoGraphListProps) {
  const { traceId, workflowSpanId, showEdgeLabels } = props

  console.log('Workflow span id: ', workflowSpanId)
  console.log('Trace id: ', traceId)

  const workflowChain = useAppSelector((state: RootState) =>
    identifySpanWorkflowChain(state, {
      traceId,
      workflowSpanId,
    }),
  )

  console.log('Workflow Chain: ', workflowChain)

  return workflowChain.map((workflowSpan) => {
    // Parse mermaid flow string
    const mermaidFlowString = JunjoGraph.fromJson(workflowSpan.junjo_wf_graph_structure).toMermaid(
      showEdgeLabels,
    )
    const uniqueMermaidId = `mer-unique-${workflowSpan.span_id}`

    // console.log(`Mermaid string ${uniqueMermaidId}:\n`, mermaidFlowString)

    return (
      <div key={`key-${uniqueMermaidId}`} className={'mb-5'}>
        <div className={'font-bold text-sm'}>{workflowSpan.name}</div>
        [Mermaid here]
        <RenderJunjoGraphMermaid
          workflowChain={workflowChain}
          mermaidFlowString={mermaidFlowString}
          mermaidUniqueId={uniqueMermaidId}
          workflowSpanId={workflowSpan.span_id}
        />
      </div>
    )
  })
}

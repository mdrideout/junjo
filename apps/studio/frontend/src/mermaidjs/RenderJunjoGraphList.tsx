import { identifyWorkflowChain, selectWorkflowSpan } from '../features/otel/store/selectors'
import { useAppSelector } from '../root-store/hooks'
import { RootState } from '../root-store/store'

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

  // // Get the top level workflow span
  // const topLevelWorkflowSpan = useAppSelector((state: RootState) =>
  //   selectWorkflowSpan(state, { serviceName, spanID: workflowSpanID }),
  // )

  // Return test span for now
  console.log('Re-rendering RenderJunjoGraphList')
  console.log('Workflow chain: ', workflowChain)
  return (
    <div>
      {workflowChain.map((workflowSpan) => {
        return <div key={workflowSpan.span_id}>{workflowSpan.name}</div>
      })}
    </div>
  )

  // // Get the chain of workflows / subflows that lead to the active span
  // const activeSpanWorkflowChain = useAppSelector((state: RootState) =>
  //   identifyWorkflowChain(state, {
  //     serviceName: activeSpan?.service_name,
  //     startingSpan: activeSpan,
  //   }),
  // )

  // // Memoize the final list of workflow spans
  // const finalWorkflowSpans = useMemo(() => {
  //   // If there is no top level workflow span, return an empty array
  //   if (!topLevelWorkflowSpan) {
  //     return []
  //   }

  //   // Filter the chain to exclude the top level workflow span
  //   const filteredWorkflowChildSpans = activeSpanWorkflowChain.filter(
  //     (workflowSpan) => workflowSpan.span_id !== topLevelWorkflowSpan.span_id,
  //   )

  //   // Create a final array of the top level workflow span and the filtered child spans
  //   return [topLevelWorkflowSpan, ...filteredWorkflowChildSpans]
  // }, [topLevelWorkflowSpan, activeSpanWorkflowChain])

  // // If there are no workflow spans to render, return null
  // if (finalWorkflowSpans.length === 0) {
  //   return null
  // }

  // console.log('Re-rendering RenderJunjoGraphList')

  // return finalWorkflowSpans.map((workflowSpan) => {
  //   // Parse mermaid flow string
  //   console.log('Junjo Graph Structure: ', workflowSpan.junjo_wf_graph_structure)
  //   const mermaidFlowString = JunjoGraph.fromJson(workflowSpan.junjo_wf_graph_structure).toMermaid(
  //     showEdgeLabels,
  //   )
  //   const mermaidUniqueId = nanoid()

  //   return (
  //     <div key={workflowSpan.span_id} className={'mb-5'}>
  //       <div>{workflowSpan.name}</div>
  //       <RenderJunjoGraphMermaid
  //         mermaidFlowString={mermaidFlowString}
  //         mermaidUniqueId={mermaidUniqueId}
  //         serviceName={serviceName}
  //         workflowSpanID={workflowSpan.span_id}
  //       />
  //     </div>
  //   )
  // })
}

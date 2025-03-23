export type WorkflowStructureProps = {
  spanID: string
}

/**
 * Workflow Structure
 * @param props
 * @returns
 */
export default function WorkflowStructure(props: WorkflowStructureProps) {
  const { spanID } = props

  return <div>Workflow Structure (React Flow) for Junjo Graph Here. {spanID}</div>

  // const { isLoading, error, workflowExecution } = useFetchWorkflowExecution(spanID)

  // if (isLoading) {
  //   return null
  // }

  // if (error || !workflowExecution) {
  //   return <div>Unable to load the workflow execution.</div>
  // }

  // // Create a JunjoGraph instance
  // const junjoGraph = JunjoGraph.fromBase64Json(workflowExecution.Structure)

  // return (
  //   <div className={`w-full h-[60px] mb-5`}>
  //     <ReactFlowJunjoGraph junjoGraph={junjoGraph} direction={ReactFlowGraphDirection.LR} />
  //   </div>
  // )
}

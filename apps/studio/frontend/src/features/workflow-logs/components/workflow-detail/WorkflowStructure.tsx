import { JunjoGraph } from '../../../../junjo-graph/junjo-graph'
import ReactFlowJunjoGraph from '../../../../react-flow/components/ReactFlowJunjoGraph'
import { ReactFlowGraphDirection } from '../../../../react-flow/dagre-layout-util'
import { useFetchWorkflowExecution } from '../../hooks/useFetchWorkflowExecution'

export type WorkflowStructureProps = {
  ExecID: string
}

/**
 * Workflow Structure
 * @param props
 * @returns
 */
export default function WorkflowStructure(props: WorkflowStructureProps) {
  const { ExecID } = props
  const { isLoading, error, workflowExecution } = useFetchWorkflowExecution(ExecID)

  if (isLoading) {
    return null
  }

  if (error || !workflowExecution) {
    return <div>Unable to load the workflow execution.</div>
  }

  // Create a JunjoGraph instance
  const junjoGraph = JunjoGraph.fromJson(workflowExecution.Structure)

  return (
    <div className={`w-full h-[60px] mb-5`}>
      <ReactFlowJunjoGraph junjoGraph={junjoGraph} direction={ReactFlowGraphDirection.LR} />
    </div>
  )
}

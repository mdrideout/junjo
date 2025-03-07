import { useQuery } from '@tanstack/react-query'
import { fetchWorkflowMetadata } from '../fetch/fetch-workflow-metadata'
import { WorkflowMetadatum } from '../schemas'
import { JunjoGraph } from '../../junjo-graph/junjo-graph'
import ReactFlowJunjoGraph from '../../react-flow/components/ReactFlowJunjoGraph'
import { ReactFlowGraphDirection } from '../../react-flow/dagre-layout-util'

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

  const {
    data: metadata,
    isLoading,
    isError,
    error,
  } = useQuery<WorkflowMetadatum, Error>({
    queryKey: ['workflowMetadata', ExecID],
    queryFn: () => fetchWorkflowMetadata(ExecID!),
    enabled: !!ExecID,
    staleTime: 1000 * 60 * 5, // 5 minutes
  })

  if (isLoading) {
    return null
  }

  if (isError) {
    return <div>Error: {error.message}</div>
  }

  if (!metadata) {
    return <div>No metadata found.</div>
  }

  // Create a JunjoGraph instance
  const junjoGraph = JunjoGraph.fromBase64Json(metadata.Structure)
  const json = junjoGraph.toJson()

  return (
    <div className="flex">
      {/* <div>
        <pre>{json}</pre>
      </div> */}
      <div className="grow">
        <div className={'h-[500px]'}>
          <ReactFlowJunjoGraph junjoGraph={junjoGraph} direction={ReactFlowGraphDirection.LR} />
        </div>
      </div>
    </div>
  )
}

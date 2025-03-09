import { useQuery } from '@tanstack/react-query'
import { fetchWorkflowMetadata } from '../fetch/fetch-workflow-metadata'
import { WorkflowMetadatum } from '../schemas'
import { JunjoGraph } from '../../junjo-graph/junjo-graph'
import ReactFlowJunjoGraph from '../../react-flow/components/ReactFlowJunjoGraph'
import { ReactFlowGraphDirection } from '../../react-flow/dagre-layout-util'
import { Resizable } from 'react-resizable'
import { useState } from 'react'

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

  const [width, setWidth] = useState(200)
  const [height, setHeight] = useState(150)

  const onResize = (event, { node, size, handle }) => {
    console.log('Changing size: ', size)
    setWidth(size.width)
    setHeight(size.height)
  }

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

  return (
    <div className={`w-full h-[60px] mb-5`}>
      <ReactFlowJunjoGraph junjoGraph={junjoGraph} direction={ReactFlowGraphDirection.LR} />
    </div>
  )
}

import { useQuery } from '@tanstack/react-query'
import { decodeBase64Json } from '../../util/decode-base64-json'
import { fetchWorkflowMetadata } from '../fetch/fetch-workflow-metadata'
import { WorkflowMetadatum } from '../schemas'

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

  // useQuery<DataType, ErrorType>
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

  const decodeStructure = decodeBase64Json(metadata.Structure)
  const displayStructure = JSON.stringify(decodeStructure, null, 2)

  return (
    <div>
      <pre>{displayStructure}</pre>
    </div>
  )
}

import { decodeBase64Json } from '../../util/decode-base64-json'
import { useMetadataStore } from '../store/workflow_metadata_store'

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
  const metadata = useMetadataStore((state) => state.metadata[ExecID])
  const structure = metadata?.Structure

  if (!structure) {
    return <div>Workflow structure not found</div>
  }

  const decodeStructure = decodeBase64Json(structure)
  const displayStructure = JSON.stringify(decodeStructure, null, 2)

  return (
    <div>
      <pre>{displayStructure}</pre>
    </div>
  )
}

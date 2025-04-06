import { JunjoGraph } from '../../../junjo-graph/junjo-graph'
import RenderJunjoGraphMermaid from '../../../mermaidjs/RenderJunjoGraphMermaid'

export type WorkflowStructureProps = {
  graph: JunjoGraph
}

/**
 * Workflow Structure
 * @param props
 * @returns
 */
export default function WorkflowStructure(props: WorkflowStructureProps) {
  const { graph } = props

  return <RenderJunjoGraphMermaid graph={graph} />
}

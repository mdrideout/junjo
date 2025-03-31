import { JunjoGraph } from '../../../junjo-graph/junjo-graph'
import ReactFlowJunjoGraph from '../../../react-flow/components/ReactFlowJunjoGraph'
import { ReactFlowGraphDirection } from '../../../react-flow/dagre-layout-util'

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

  return (
    <div className={`w-full h-[250px] mb-5`}>
      <ReactFlowJunjoGraph junjoGraph={graph} direction={ReactFlowGraphDirection.LR} />
    </div>
  )
}

import { ArrowLeftIcon, ArrowRightIcon } from '@radix-ui/react-icons'
import { useActiveNodeContext } from './ActiveNodeContext'
import { NodeSetStateEvent } from '../../otel/store/schemas'

interface WorkflowStateEventNavButtonsProps {
  workflowStateEvents: NodeSetStateEvent[]
}

export default function WorkflowStateEventNavButtons(props: WorkflowStateEventNavButtonsProps) {
  const { workflowStateEvents } = props
  const { activeNodeSetStateEvent, setActiveNodeSetStateEvent, setScrollToPatchId } = useActiveNodeContext()
  const activePatchIndex = workflowStateEvents.findIndex(
    (patch) => patch.attributes.id === activeNodeSetStateEvent?.attributes.id,
  )

  const disablePrev = activePatchIndex === 0
  const disableNext = activePatchIndex + 1 === workflowStateEvents.length

  const handleNextPatchClick = () => {
    if (activeNodeSetStateEvent) {
      const nextPatchIndex = activePatchIndex + 1
      if (nextPatchIndex < workflowStateEvents.length) {
        const nextPatch = workflowStateEvents[nextPatchIndex]
        setActiveNodeSetStateEvent(nextPatch)
        setScrollToPatchId(nextPatch.attributes.id)
      }
    }
  }

  const handlePrevPatchClick = () => {
    if (activeNodeSetStateEvent) {
      const prevPatchIndex = activePatchIndex - 1
      if (prevPatchIndex >= 0) {
        const prevPatch = workflowStateEvents[prevPatchIndex]
        setActiveNodeSetStateEvent(prevPatch)
        setScrollToPatchId(prevPatch.attributes.id)
      }
    }
  }

  return (
    <div className={'flex gap-x-1'}>
      <button
        className={
          'border border-zinc-300 rounded-md p-[0px] hover:bg-zinc-300 cursor-pointer disabled:opacity-20'
        }
        onClick={handlePrevPatchClick}
        disabled={disablePrev}
      >
        <ArrowLeftIcon />
      </button>

      <button
        className={
          'border border-zinc-300 rounded-md p-[0px] hover:bg-zinc-300 cursor-pointer disabled:opacity-20'
        }
        onClick={handleNextPatchClick}
        disabled={disableNext}
      >
        <ArrowRightIcon />
      </button>
    </div>
  )
}

import { ArrowLeftIcon, ArrowRightIcon } from '@radix-ui/react-icons'
import { useActiveSpanContext } from './ActiveNodeContext'
import { JunjoSetStateEvent } from '../../otel/store/schemas'
import { useAppSelector } from '../../../root-store/hooks'
import { RootState } from '../../../root-store/store'
import { selectStateEventParentSpan } from '../../otel/store/selectors'
import { useEffect } from 'react'

interface WorkflowStateEventNavButtonsProps {
  serviceName: string
  workflowSpanID: string
  workflowStateEvents: JunjoSetStateEvent[]
}

export default function WorkflowStateEventNavButtons(props: WorkflowStateEventNavButtonsProps) {
  const { serviceName, workflowSpanID, workflowStateEvents } = props
  const { activeSetStateEvent, setActiveSetStateEvent, setActiveSpan, setScrollToSpanId } =
    useActiveSpanContext()

  // Get the span that contains this workflow state event
  const span = useAppSelector((state: RootState) =>
    selectStateEventParentSpan(state, {
      serviceName,
      workflowSpanID,
      stateEventId: activeSetStateEvent?.attributes.id,
    }),
  )

  // Get the index of the active patch
  const activePatchIndex = workflowStateEvents.findIndex(
    (patch) => patch.attributes.id === activeSetStateEvent?.attributes.id,
  )

  const disablePrev = activePatchIndex === 0
  const disableNext = activePatchIndex + 1 === workflowStateEvents.length

  // Effect to update the active span when the activeSetStateEvent changes
  useEffect(() => {
    if (span) {
      setActiveSpan(span)
    }
    // Add dependencies: setActiveSpan and span
    // activeSetStateEvent is implicitly a dependency because `span` depends on it.
  }, [span, setActiveSpan])

  const handleNextPatchClick = () => {
    if (activeSetStateEvent) {
      const nextPatchIndex = activePatchIndex + 1
      if (nextPatchIndex < workflowStateEvents.length) {
        const nextPatch = workflowStateEvents[nextPatchIndex]
        setActiveSetStateEvent(nextPatch)
        setScrollToSpanId(nextPatch.attributes.id)
      }
    }
  }

  const handlePrevPatchClick = () => {
    if (activeSetStateEvent) {
      const prevPatchIndex = activePatchIndex - 1
      if (prevPatchIndex >= 0) {
        const prevPatch = workflowStateEvents[prevPatchIndex]
        setActiveSetStateEvent(prevPatch)
        setScrollToSpanId(prevPatch.attributes.id)
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

import { ArrowLeftIcon, ArrowRightIcon } from '@radix-ui/react-icons'
import { JunjoSetStateEvent } from '../../otel/store/schemas'
import { useAppDispatch, useAppSelector } from '../../../root-store/hooks'
import { RootState } from '../../../root-store/store'
import { selectStateEventParentSpan } from '../../otel/store/selectors'
import { useEffect } from 'react'
import { WorkflowDetailStateActions } from './store/slice'

interface WorkflowStateEventNavButtonsProps {
  serviceName: string
  workflowSpanID: string
  workflowStateEvents: JunjoSetStateEvent[]
}

export default function WorkflowStateEventNavButtons(props: WorkflowStateEventNavButtonsProps) {
  const { serviceName, workflowSpanID, workflowStateEvents } = props
  const dispatch = useAppDispatch()

  const activeSetStateEvent = useAppSelector(
    (state: RootState) => state.workflowDetailState.activeSetStateEvent,
  )

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
      dispatch(WorkflowDetailStateActions.setActiveSpan(span))
    }
  }, [span, dispatch])

  const handleNextPatchClick = () => {
    if (activeSetStateEvent) {
      const nextPatchIndex = activePatchIndex + 1
      if (nextPatchIndex < workflowStateEvents.length) {
        const nextPatch = workflowStateEvents[nextPatchIndex]
        dispatch(WorkflowDetailStateActions.setActiveSetStateEvent(nextPatch))
        dispatch(WorkflowDetailStateActions.setScrollToStateEventId(nextPatch.attributes.id))
      }
    }
  }

  const handlePrevPatchClick = () => {
    if (activeSetStateEvent) {
      const prevPatchIndex = activePatchIndex - 1
      if (prevPatchIndex >= 0) {
        const prevPatch = workflowStateEvents[prevPatchIndex]
        dispatch(WorkflowDetailStateActions.setActiveSetStateEvent(prevPatch))
        console.log(`Scrolling to span ID: ${prevPatch.attributes.id}`)
        dispatch(WorkflowDetailStateActions.setScrollToStateEventId(prevPatch.attributes.id))
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

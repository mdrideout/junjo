import { ArrowLeftIcon, ArrowRightIcon } from '@radix-ui/react-icons'
import { useMemo } from 'react'
import { useAppDispatch, useAppSelector } from '../../../root-store/hooks'
import type { RootState } from '../../../root-store/store'
import type { StoreTransition } from '../../store-diagnostics/schemas/store-diagnostics'
import { JunjoSetStateEventSchema } from '../../traces/schemas/schemas'
import { selectTraceSpansForTraceId } from '../../traces/store/selectors'
import { spanSelection, WorkflowDetailStateActions } from './store/slice'
import {
  rawStateEventIdentity,
  stateEventIdentityKey,
  transitionStateEventIdentity,
} from './state-event-identity'
import { useNavigate } from 'react-router'
import { useWorkflowDetailRoute } from './workflow-detail-route-context'
import { workflowPath } from '../../../util/telemetry-paths'

interface WorkflowStateEventNavButtonsProps {
  traceId: string
  storeId: string | null
  transitions: StoreTransition[]
}

export default function WorkflowStateEventNavButtons({
  traceId,
  storeId,
  transitions,
}: WorkflowStateEventNavButtonsProps) {
  const dispatch = useAppDispatch()
  const navigate = useNavigate()
  const route = useWorkflowDetailRoute()
  const activeStateEvent = useAppSelector(
    (state: RootState) => state.workflowDetailState.activeStateEvent,
  )
  const traceSpans = useAppSelector((state: RootState) =>
    selectTraceSpansForTraceId(state, { traceId }),
  )
  const orderedTransitions = useMemo(
    () => [...transitions].sort((left, right) => left.sequence - right.sequence),
    [transitions],
  )
  const rawEventsByIdentity = useMemo(() => {
    const events = new Map<string, ReturnType<typeof JunjoSetStateEventSchema.parse>>()
    for (const span of traceSpans) {
      for (const event of span.events_json) {
        const parsed = JunjoSetStateEventSchema.safeParse(event)
        if (parsed.success) {
          events.set(
            stateEventIdentityKey(rawStateEventIdentity(span.span_id, parsed.data)),
            parsed.data,
          )
        }
      }
    }
    return events
  }, [traceSpans])
  const spansById = useMemo(
    () => new Map(traceSpans.map((span) => [span.span_id, span])),
    [traceSpans],
  )
  const activeTransitionIndex = orderedTransitions.findIndex(
    (transition) => storeId !== null
      && activeStateEvent !== null
      && stateEventIdentityKey(transitionStateEventIdentity(storeId, transition))
      === stateEventIdentityKey(activeStateEvent),
  )
  const hasActiveTransition = activeTransitionIndex >= 0
  const disablePrev = !hasActiveTransition || activeTransitionIndex === 0
  const disableNext = !hasActiveTransition || activeTransitionIndex + 1 === orderedTransitions.length

  const selectTransition = (transition: StoreTransition) => {
    if (storeId === null) return
    const identity = transitionStateEventIdentity(storeId, transition)
    const event = rawEventsByIdentity.get(stateEventIdentityKey(identity))
    const span = spansById.get(transition.span_id)
    if (event === undefined || span === undefined) return

    dispatch(WorkflowDetailStateActions.selectSpan(spanSelection(span)))
    dispatch(WorkflowDetailStateActions.setActiveStateEvent({ ...identity, event }))
    dispatch(WorkflowDetailStateActions.setStateEventScrollTarget(identity))
    navigate(workflowPath(
      route.serviceName,
      route.traceId,
      route.workflowSpanId,
      span.span_id,
    ), { replace: true })
  }

  return (
    <div className="flex gap-x-2 -mt-[1px]">
      {hasActiveTransition && (
        <div>
          ({activeTransitionIndex + 1} / {orderedTransitions.length}){' '}
        </div>
      )}
      <button
        aria-label="Previous Store transition"
        className="border border-zinc-300 rounded-md p-[0px] hover:bg-zinc-300 cursor-pointer disabled:opacity-20"
        onClick={() => selectTransition(orderedTransitions[activeTransitionIndex - 1])}
        disabled={disablePrev}
      >
        <ArrowLeftIcon />
      </button>
      <button
        aria-label="Next Store transition"
        className="border border-zinc-300 rounded-md p-[0px] hover:bg-zinc-300 cursor-pointer disabled:opacity-20"
        onClick={() => selectTransition(orderedTransitions[activeTransitionIndex + 1])}
        disabled={disableNext}
      >
        <ArrowRightIcon />
      </button>
    </div>
  )
}

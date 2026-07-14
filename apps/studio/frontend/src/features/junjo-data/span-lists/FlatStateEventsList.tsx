import { PlayIcon } from '@heroicons/react/24/solid'
import { useEffect, useMemo, useRef } from 'react'
import { useAppDispatch, useAppSelector } from '../../../root-store/hooks'
import type { RootState } from '../../../root-store/store'
import {
  formatMicrosecondsSinceEpochToTime,
  nanosecondsStringToMicroseconds,
} from '../../../util/duration-utils'
import type { WorkflowStoreDiagnosticRequest } from '../../workflow-executions/hooks/use-workflow-store-diagnostic'
import { JunjoSetStateEventSchema } from '../../traces/schemas/schemas'
import { selectSpanAndChildren } from '../../traces/store/selectors'
import { WorkflowDetailStateActions } from '../workflow-detail/store/slice'
import {
  rawStateEventIdentity,
  stateEventIdentityKey,
  transitionStateEventIdentity,
} from '../workflow-detail/state-event-identity'
import { SpanIconConstructor } from './determine-span-icon'

interface FlatStateEventsListProps {
  traceId: string
  workflowSpanId: string
  storeDiagnosticRequest: WorkflowStoreDiagnosticRequest
}

/** Render one Store owner's transitions in backend-verified sequence order. */
export default function FlatStateEventsList({
  traceId,
  workflowSpanId,
  storeDiagnosticRequest,
}: FlatStateEventsListProps) {
  const scrollableContainerRef = useRef<HTMLDivElement>(null)
  const transitionRowRefs = useRef(new Map<string, HTMLButtonElement>())
  const dispatch = useAppDispatch()
  const spans = useAppSelector((state: RootState) =>
    selectSpanAndChildren(state, { traceId, spanId: workflowSpanId }),
  )
  const activeStateEvent = useAppSelector(
    (state: RootState) => state.workflowDetailState.activeStateEvent,
  )
  const activeSpan = useAppSelector((state: RootState) => state.workflowDetailState.activeSpan)
  const stateEventScrollTarget = useAppSelector(
    (state: RootState) => state.workflowDetailState.stateEventScrollTarget,
  )
  const transitions = useMemo(
    () => [...(storeDiagnosticRequest.data?.state.transitions ?? [])].sort(
      (left, right) => left.sequence - right.sequence,
    ),
    [storeDiagnosticRequest.data],
  )
  const spansById = useMemo(
    () => new Map(spans.map((span) => [span.span_id, span])),
    [spans],
  )
  const rawEventsByIdentity = useMemo(() => {
    const events = new Map<string, ReturnType<typeof JunjoSetStateEventSchema.parse>>()
    for (const span of spans) {
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
  }, [spans])

  useEffect(() => {
    if (stateEventScrollTarget === null || scrollableContainerRef.current === null) return
    const target = transitionRowRefs.current.get(stateEventIdentityKey(stateEventScrollTarget))
    target?.scrollIntoView({ behavior: 'smooth', block: 'nearest', inline: 'nearest' })
  }, [stateEventScrollTarget])

  if (storeDiagnosticRequest.loading) {
    return <div className="px-2 py-3 text-sm text-zinc-500">Loading Store transitions…</div>
  }
  if (storeDiagnosticRequest.error !== null) {
    return <div className="px-2 py-3 text-sm text-red-700">{storeDiagnosticRequest.error}</div>
  }
  if (transitions.length === 0) {
    return <div className="px-2 py-3 text-sm text-zinc-500">No backend-projected Store transitions.</div>
  }

  return (
    <div ref={scrollableContainerRef} className="flex flex-col text-sm">
      {transitions.map((transition) => {
        const storeId = storeDiagnosticRequest.data?.state.store_id
        const identity = storeId === null || storeId === undefined
          ? null
          : transitionStateEventIdentity(storeId, transition)
        const identityKey = identity === null ? null : stateEventIdentityKey(identity)
        const event = identityKey === null ? undefined : rawEventsByIdentity.get(identityKey)
        const span = spansById.get(transition.span_id)
        const isActivePatch = identityKey !== null
          && activeStateEvent !== null
          && identityKey === stateEventIdentityKey(activeStateEvent)
        const isActiveSpan = span?.span_id === activeSpan?.span_id
        const eventTime = event === undefined
          ? null
          : formatMicrosecondsSinceEpochToTime(
            nanosecondsStringToMicroseconds(event.timeUnixNano),
          )
        const storeLabel = event?.attributes['junjo.store.name']
          ?? storeDiagnosticRequest.data?.state.store_id
          ?? 'Store'
        const selectable = event !== undefined && span !== undefined
        const activeStyle = isActivePatch
          ? 'bg-amber-100 dark:bg-amber-950'
          : isActiveSpan
            ? 'bg-zinc-100 dark:bg-zinc-800'
            : ''

        return (
          <button
            type="button"
            key={identityKey ?? `${transition.span_id}:${transition.sequence}`}
            ref={(element) => {
              if (identityKey === null) return
              if (element === null) transitionRowRefs.current.delete(identityKey)
              else transitionRowRefs.current.set(identityKey, element)
            }}
            data-state-event-id={transition.event_id}
            data-state-event-span-id={transition.span_id}
            data-state-event-sequence={transition.sequence}
            className={`flat-span-${transition.span_id} px-2 py-2 text-left flex justify-between items-start border-b last:border-0 border-zinc-200 dark:border-zinc-700 disabled:cursor-not-allowed ${selectable ? 'cursor-pointer' : ''} ${activeStyle}`}
            disabled={!selectable}
            onClick={() => {
              if (event === undefined || span === undefined) return
              dispatch(WorkflowDetailStateActions.setActiveSpan(span))
              if (identity !== null) {
                dispatch(WorkflowDetailStateActions.setActiveStateEvent({ ...identity, event }))
              }
            }}
          >
            <div className="flex gap-x-1 items-start">
              <div className="mt-[1px]">
                <SpanIconConstructor span={span} active={isActiveSpan} size="size-3.5" />
              </div>
              <div className="font-normal text-xs">
                <div className="mb-0.5 font-bold">{span?.name}</div>
                <div className="flex gap-x-1 items-center">
                  <PlayIcon className="size-3.5 text-orange-300" />
                  {transition.sequence}. {storeLabel} &rarr; {transition.action}
                </div>
                <div className="opacity-50 text-xs pl-[18.5px]">{transition.event_id}</div>
              </div>
            </div>
            {eventTime !== null && (
              <div className="font-mono text-zinc-500 text-xs">{eventTime}</div>
            )}
          </button>
        )
      })}
      <div className="h-4"></div>
    </div>
  )
}

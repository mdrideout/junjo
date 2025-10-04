import { useEffect, useMemo, useRef, useState } from 'react'
import JsonView from '@uiw/react-json-view'
import { lightTheme } from '@uiw/react-json-view/light'
import { vscodeTheme } from '@uiw/react-json-view/vscode'
import { detailedDiff, diff } from 'deep-object-diff'
import { TriangleDownIcon } from '@radix-ui/react-icons'
import { useAppSelector } from '../../../root-store/hooks'
import { RootState } from '../../../root-store/store'
import * as jsonpatch from 'fast-json-patch'
import { OtelSpan } from '../../traces/schemas/schemas'
import SpanExceptionsList from './SpanExceptionsList'
import {
  selectActiveSpanJunjoWorkflow,
  selectActiveStoreID,
  selectBeforeSpanStateEventInWorkflow,
  selectStateEventsByJunjoStoreId,
  selectWorkflowSpanByStoreId,
} from '../../traces/store/selectors'
import { ExclamationTriangleIcon } from '@heroicons/react/24/solid'
import SpanAttributesContent from '../../traces/SpanAttributesContent'

enum DiffTabOptions {
  BEFORE = 'Before',
  AFTER = 'After',
  PATCH = 'Patch',
  CHANGES = 'Changes',
  DETAILED = 'Detailed',
  EXCEPTIONS = 'Node Exceptions',
  SPAN_DETAILS = 'Span Details',
}

interface WorkflowDetailStateDiffProps {
  defaultWorkflowSpan: OtelSpan // The default workflow span is the top level workflow span
}

/**
 * Abstracted Button
 */
const TabButton = ({
  tab,
  activeTab,
  tabChangeHandler,
}: {
  tab: DiffTabOptions
  activeTab: DiffTabOptions
  tabChangeHandler: (tab: DiffTabOptions) => void
}) => {
  return (
    <button
      className={`leading-tight px-2 py-1 hover:bg-zinc-100 dark:hover:bg-zinc-700 text-sm font-medium border-b transition-all duration-200 cursor-pointer ${activeTab === tab ? 'border-zinc-600 ' : 'border-transparent'}`}
      onClick={() => tabChangeHandler(tab)}
    >
      <div className={'flex items-center gap-x-1 text-left'}>
        {tab === DiffTabOptions.EXCEPTIONS && <ExclamationTriangleIcon className={'size-5 text-red-700'} />}
        {tab}
      </div>
    </button>
  )
}

/**
 * Workflow Log State Diff
 * @param props
 * @returns
 */
export default function WorkflowDetailStateDiff(props: WorkflowDetailStateDiffProps) {
  const { defaultWorkflowSpan } = props
  const hasMountedRef = useRef(false)

  const openExceptionsTrigger = useAppSelector(
    (state: RootState) => state.workflowDetailState.openExceptionsTrigger,
  )
  const activeSpan = useAppSelector((state: RootState) => state.workflowDetailState.activeSpan)
  const activeSetStateEvent = useAppSelector(
    (state: RootState) => state.workflowDetailState.activeSetStateEvent,
  )
  const hasExceptions =
    activeSpan?.events_json.some((event) => {
      return event.attributes && event.attributes['exception.type'] !== undefined
    }) ?? false

  // Get All Workflow State Events
  // This includes the default top level workflow and all subflows
  // The active workflow span is the workflow with store.id matching the activeStoreID,
  // defaulting to the default workflow span if there is no active set state event
  // This may be a subflow of the default workflow depending on the set state event
  const activeWorkflowSpan = useAppSelector((state: RootState) => selectActiveSpanJunjoWorkflow(state))

  // The Active Store is the store that the active span is acting on
  const activeStoreId = useAppSelector((state: RootState) => selectActiveStoreID(state))

  // This is the workflow span that owns the store that the active span is acting on
  // The active span may be a subflow operating on a parent store.
  const activeStoreWorkflowSpan = useAppSelector((state: RootState) =>
    selectWorkflowSpanByStoreId(state, {
      traceId: defaultWorkflowSpan.trace_id,
      storeId: activeStoreId,
    }),
  )

  // Get Active Workflow State Events
  // This is only state events for the currently actively rendering workflow or subflow
  // This is so we can construct the patches of just this rendered JSON state for this workflow and its store
  // This will not include state events of parent or child stores
  const activeStoreStateEvents = useAppSelector((state: RootState) =>
    selectStateEventsByJunjoStoreId(state, {
      traceId: activeWorkflowSpan?.trace_id,
      spanId: activeWorkflowSpan?.span_id,
      storeId: activeStoreId,
    }),
  )

  // The starting state of the active workflow
  // Used for accumulating patches
  const workflowStateStart = activeStoreWorkflowSpan?.junjo_wf_state_start ?? {}

  // Workflow JSON States
  // Different representations of the Workflow's states for rendering
  const [beforeJson, setBeforeJson] = useState<object>(workflowStateStart)
  const [afterJson, setAfterJson] = useState<object>(workflowStateStart)

  // Select: Gets the last set_state event before the active span
  const beforeActiveSpanStateEvent = useAppSelector((state: RootState) =>
    selectBeforeSpanStateEventInWorkflow(state, {
      traceId: activeWorkflowSpan?.trace_id,
      spanId: activeWorkflowSpan?.span_id,
      storeId: activeStoreId,
    }),
  )

  // Local State
  const [activeTab, setActiveTab] = useState<DiffTabOptions>(
    activeSetStateEvent ? DiffTabOptions.AFTER : DiffTabOptions.SPAN_DETAILS,
  )
  const [prefersDarkMode, setPrefersDarkMode] = useState<boolean>(false)

  // Infer Changes & Detailed tab data using deep-object-diff
  const changesJson = diff(beforeJson, afterJson)
  const detailedJson = detailedDiff(beforeJson, afterJson)

  const patchJson = useMemo(() => {
    const patchString = activeSetStateEvent?.attributes['junjo.state_json_patch']
    if (!patchString) return {}
    try {
      return JSON.parse(patchString)
    } catch (e) {
      console.error('Failed to parse patch string', e)
      return { error: 'Failed to parse patch JSON' }
    }
  }, [activeSetStateEvent])

  // JSON Renderer Theme Decider
  const displayTheme = prefersDarkMode ? vscodeTheme : lightTheme

  // Detect preferred color scheme
  useEffect(() => {
    const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)')
    setPrefersDarkMode(mediaQuery.matches)

    const listener = (event: MediaQueryListEvent) => {
      setPrefersDarkMode(event.matches)
    }

    mediaQuery.addEventListener('change', listener)
    return () => mediaQuery.removeEventListener('change', listener)
  }, [])

  // Detect openExceptions trigger and set the active tab to exceptions
  useEffect(() => {
    // skip on first render
    if (!hasMountedRef.current) {
      hasMountedRef.current = true
      return
    }
    // only switch if we actually got a new trigger
    if (openExceptionsTrigger != null) {
      setActiveTab(DiffTabOptions.EXCEPTIONS)
    }
  }, [openExceptionsTrigger])

  // Detect if there are no exceptions, and we are on the exceptions tab, and switch to After tab
  useEffect(() => {
    if (activeTab === DiffTabOptions.EXCEPTIONS && !hasExceptions) {
      setActiveTab(DiffTabOptions.AFTER)
    }
  }, [activeTab, hasExceptions])

  // When the active state event is cleared, go to the span details tab
  // When a state event is selected, and we are on the span details tab, go to the after tab
  useEffect(() => {
    if (activeSetStateEvent === null) {
      setActiveTab(DiffTabOptions.SPAN_DETAILS)
    } else {
      if (activeTab === DiffTabOptions.SPAN_DETAILS) {
        setActiveTab(DiffTabOptions.AFTER)
      }
    }
  }, [activeSetStateEvent, activeTab])

  /**
   * Accumulate State Patches To Index (inclusive)
   *
   * Given a patch index, this function will accumulate the patches up to and including the patch at the given index.
   *
   * @returns {[Record<string, any>, Record<string, any>]} - before / after state
   */
  const accumulateStatePathesToIndex = (patchIndex: number): [Record<string, any>, Record<string, any>] => {
    // If there are no patches, just set the original state
    if (activeStoreStateEvents.length === 0) {
      return [workflowStateStart, workflowStateStart]
    }

    // If the patch index is out of bounds, return (there is no patch)
    if (patchIndex < 0 || patchIndex >= activeStoreStateEvents.length) {
      return [workflowStateStart, workflowStateStart]
    }

    // Starting points for accumulating patches
    let beforeCumulativeState = structuredClone(workflowStateStart)
    let afterCumulativeState = structuredClone(workflowStateStart)

    // Apply patches to the cumulative state
    for (let i = 0; i <= patchIndex; i++) {
      const thisEvent = activeStoreStateEvents[i]

      const patchString = thisEvent.attributes['junjo.state_json_patch']
      const patch = JSON.parse(patchString)
      // console.log(`Patch ${i} of ${patchIndex}`)
      // console.log('Patch string: ', patchString)
      // console.log('Patch: ', patch)

      // Apply to after state
      afterCumulativeState = jsonpatch.applyPatch(afterCumulativeState, patch).newDocument

      // Apply to before state if i is less than patchIndex
      if (i < patchIndex) {
        beforeCumulativeState = jsonpatch.applyPatch(beforeCumulativeState, patch).newDocument
      }
    }

    return [beforeCumulativeState, afterCumulativeState]
  }

  /**
   * Run the patch accumulation functions based on the active span / active state event
   */
  useEffect(() => {
    // If there is no active set state event,
    // use the index of the set_state event that occurs most recently before
    // the active span start time
    // NOTE: THIS DEPENDS ON THE AUTOMATIC SELECTION OF THE FIRST STATE EVENT INSIDE SPANS WITH STATE EVENTS
    //       OTHERWISE, the ux diffs may not make sense.
    //       Spans with no state events have the same before / after state (equal to the AFTER state of the most recent prior state event)
    if (!activeSetStateEvent) {
      // The index of the set state event that occurs just prior to the active span, in the list of state events for the active workflow's store
      const indexOfBeforeActiveSpanSetStateEventInsideActiveStore = activeStoreStateEvents.findIndex(
        (event) => event.attributes.id === beforeActiveSpanStateEvent?.attributes.id,
      )
      const [_before, after] = accumulateStatePathesToIndex(
        indexOfBeforeActiveSpanSetStateEventInsideActiveStore,
      )
      setBeforeJson(after)
      setAfterJson(after)
      return
    }

    // If there is an active set state event, use the index of that event
    // The before / after is based on the before patch state, and after patch state
    const indexOfActiveSetStateEventInsideActiveStore = activeStoreStateEvents.findIndex(
      (event) => event.attributes.id === activeSetStateEvent?.attributes.id,
    )
    const [before, after] = accumulateStatePathesToIndex(indexOfActiveSetStateEventInsideActiveStore)
    setBeforeJson(before)
    setAfterJson(after)
  }, [activeStoreStateEvents, activeWorkflowSpan, activeSetStateEvent, beforeActiveSpanStateEvent])

  // Get Tab Collapsed Level
  const getTabCollapsedLevel = (tab: DiffTabOptions) => {
    switch (tab) {
      case DiffTabOptions.CHANGES:
        return 2
      case DiffTabOptions.PATCH:
        return 3
      default:
        return 2
    }
  }

  // Get Tab JSON Data
  const getTabJsonData = (tab: DiffTabOptions) => {
    switch (tab) {
      case DiffTabOptions.BEFORE:
        return beforeJson
      case DiffTabOptions.AFTER:
        return afterJson
      case DiffTabOptions.CHANGES:
        return changesJson
      case DiffTabOptions.DETAILED:
        return detailedJson
      case DiffTabOptions.PATCH:
        return patchJson
      default:
        return {}
    }
  }

  return (
    <div className={'flex-1/2 flex flex-col pr-2.5'}>
      <div className={'flex gap-x-2 items-center'}>
        <div className={`leading-tight pl-2 py-1 text-sm font-bold`}>State:</div>
        <TabButton tab={DiffTabOptions.BEFORE} activeTab={activeTab} tabChangeHandler={setActiveTab} />
        <TabButton tab={DiffTabOptions.AFTER} activeTab={activeTab} tabChangeHandler={setActiveTab} />
        {activeSetStateEvent && (
          <TabButton tab={DiffTabOptions.PATCH} activeTab={activeTab} tabChangeHandler={setActiveTab} />
        )}
        <TabButton tab={DiffTabOptions.CHANGES} activeTab={activeTab} tabChangeHandler={setActiveTab} />
        <TabButton tab={DiffTabOptions.DETAILED} activeTab={activeTab} tabChangeHandler={setActiveTab} />|
        {activeSpan && (
          <TabButton
            tab={DiffTabOptions.SPAN_DETAILS}
            activeTab={activeTab}
            tabChangeHandler={setActiveTab}
          />
        )}
        {hasExceptions && (
          <TabButton tab={DiffTabOptions.EXCEPTIONS} activeTab={activeTab} tabChangeHandler={setActiveTab} />
        )}
      </div>
      {/* Exception View */}
      {activeSpan && activeTab === DiffTabOptions.EXCEPTIONS && (
        <div className={'grow overflow-y-scroll border-t border-zinc-200 dark:border-zinc-700'}>
          <SpanExceptionsList spans={[activeSpan]} />
        </div>
      )}
      {/* Attributes View */}
      {activeSpan && activeTab === DiffTabOptions.SPAN_DETAILS && (
        <div className={'grow overflow-y-scroll border-t border-zinc-200 dark:border-zinc-700 p-4'}>
          <SpanAttributesContent span={activeSpan} />
        </div>
      )}
      {/* JSON View */}
      {activeTab !== DiffTabOptions.EXCEPTIONS && activeTab !== DiffTabOptions.SPAN_DETAILS && (
        <div
          className={
            'workflow-logs-json-container grow overflow-y-scroll border-t border-zinc-200 dark:border-zinc-700'
          }
        >
          <JsonView
            key={JSON.stringify(getTabJsonData(activeTab))}
            value={getTabJsonData(activeTab)}
            collapsed={getTabCollapsedLevel(activeTab)}
            shouldExpandNodeInitially={(isExpanded, { value, level }) => {
              // Collapse arrays more than 1 level deep (not root arrays)
              const isArray = Array.isArray(value)
              if (isArray && level > 1) {
                const arrayLength = Object.keys(value).length

                // Only hide if the array length is greater than 1
                if (arrayLength > 1) {
                  return true
                }
              }

              return isExpanded
            }}
            style={{ ...displayTheme, fontFamily: 'var(--font-mono)' }}
          >
            {/* Zero width whitespace char */}
            <JsonView.Quote>&#8203;</JsonView.Quote>
            <JsonView.Arrow>
              <TriangleDownIcon className={'size-4 leading-0'} />
            </JsonView.Arrow>
          </JsonView>
        </div>
      )}
    </div>
  )
}

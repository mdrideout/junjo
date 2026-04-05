import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import JsonView from '@uiw/react-json-view'
import { lightTheme } from '@uiw/react-json-view/light'
import { vscodeTheme } from '@uiw/react-json-view/vscode'
import { detailedDiff, diff } from 'deep-object-diff'
import { TriangleDownIcon } from '@radix-ui/react-icons'
import { useAppSelector } from '../../../root-store/hooks'
import { RootState } from '../../../root-store/store'
import * as jsonpatch from 'fast-json-patch'
import { OtelSpan } from '../../traces/schemas/schemas'
import SpanFailuresList from './SpanFailuresList'
import {
  selectActiveSpanJunjoWorkflow,
  selectActiveStoreID,
  selectBeforeSpanStateEventInWorkflow,
  selectStateEventsByJunjoStoreId,
  selectWorkflowSpanByStoreId,
} from '../../traces/store/selectors'
import { ExclamationTriangleIcon } from '@heroicons/react/24/solid'
import SpanAttributesContent from '../../traces/SpanAttributesContent'
import { wrapSpan } from '../../traces/utils/span-accessor'

enum DiffTabOptions {
  BEFORE = 'Before',
  AFTER = 'After',
  PATCH = 'Patch',
  CHANGES = 'Changes',
  DETAILED = 'Detailed',
  FAILURES = 'Failures',
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
        {tab === DiffTabOptions.FAILURES && <ExclamationTriangleIcon className={'size-4 text-red-700'} />}
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

  const openFailuresTrigger = useAppSelector(
    (state: RootState) => state.workflowDetailState.openFailuresTrigger,
  )
  const activeSpan = useAppSelector((state: RootState) => state.workflowDetailState.activeSpan)
  const activeSetStateEvent = useAppSelector(
    (state: RootState) => state.workflowDetailState.activeSetStateEvent,
  )
  const hasFailures = activeSpan ? wrapSpan(activeSpan).hasFailureSignal : false

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
  const workflowStateStart = useMemo(
    () => (activeStoreWorkflowSpan ? wrapSpan(activeStoreWorkflowSpan).workflowStateStart : {}),
    [activeStoreWorkflowSpan],
  )

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

  // Default Tab
  const defaultTab = activeSetStateEvent ? DiffTabOptions.AFTER : DiffTabOptions.SPAN_DETAILS

  // Local State
  const [activeTab, setActiveTab] = useState<DiffTabOptions>(defaultTab)
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

  // Detect openFailures trigger and set the active tab to failures
  useEffect(() => {
    // skip on first render
    if (!hasMountedRef.current) {
      hasMountedRef.current = true
      return
    }
    // only switch if we actually got a new trigger
    if (openFailuresTrigger != null) {
      setActiveTab(DiffTabOptions.FAILURES)
    }
  }, [openFailuresTrigger])

  // Detect if there are no failures, and we are on the failures tab, and switch to the default tab
  useEffect(() => {
    if (activeTab === DiffTabOptions.FAILURES && !hasFailures) {
      setActiveTab(defaultTab)
    }
  }, [activeTab, defaultTab, hasFailures])

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
   * Ensure parent paths exist for array index operations.
   * When a patch like {"op":"add","path":"/foo/0"} is applied,
   * the parent path "/foo" must exist as an array.
   */
  const ensureParentPathsExist = useCallback((doc: Record<string, unknown>, patch: jsonpatch.Operation[]): void => {
    for (const op of patch) {
      if (op.op === 'add' && op.path) {
        const pathParts = op.path.split('/').filter(Boolean)
        let current: Record<string, unknown> | unknown[] = doc

        // Walk through path parts except the last one (which is the target)
        for (let i = 0; i < pathParts.length - 1; i++) {
          const part = pathParts[i]
          const nextPart = pathParts[i + 1]
          const shouldCreateArray = /^\d+$/.test(nextPart)

          if (Array.isArray(current)) {
            const index = Number(part)
            if (current[index] === undefined) {
              current[index] = shouldCreateArray ? [] : {}
            }

            const nextValue = current[index]
            if (typeof nextValue !== 'object' || nextValue === null) {
              break
            }

            current = nextValue as Record<string, unknown> | unknown[]
            continue
          }

          if (current[part] === undefined) {
            current[part] = shouldCreateArray ? [] : {}
          }

          const nextValue = current[part]
          if (typeof nextValue !== 'object' || nextValue === null) {
            break
          }

          current = nextValue as Record<string, unknown> | unknown[]
        }
      }
    }
  }, [])

  /**
   * Accumulate State Patches To Index (inclusive)
   *
   * Given a patch index, this function will accumulate the patches up to and including the patch at the given index.
   *
   * @returns {[Record<string, unknown>, Record<string, unknown>]} - before / after state
   */
  const accumulateStatePathesToIndex = useCallback((
    patchIndex: number,
  ): [Record<string, unknown>, Record<string, unknown>] => {
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
      let patch: jsonpatch.Operation[]
      try {
        const parsedPatch = JSON.parse(patchString) as unknown
        if (!Array.isArray(parsedPatch)) {
          throw new Error('Patch payload is not an array')
        }
        patch = parsedPatch as jsonpatch.Operation[]
      } catch (e) {
        console.error('Failed to parse patch string', e)
        continue
      }

      // Ensure parent paths exist before applying patch (handles array index adds)
      ensureParentPathsExist(afterCumulativeState, patch)

      // Apply to after state
      try {
        afterCumulativeState = jsonpatch.applyPatch<Record<string, unknown>>(afterCumulativeState, patch)
          .newDocument
      } catch (e) {
        console.error('Failed to apply patch to after state', e, patch)
      }

      // Apply to before state if i is less than patchIndex
      if (i < patchIndex) {
        ensureParentPathsExist(beforeCumulativeState, patch)
        try {
          beforeCumulativeState = jsonpatch.applyPatch<Record<string, unknown>>(beforeCumulativeState, patch)
            .newDocument
        } catch (e) {
          console.error('Failed to apply patch to before state', e, patch)
        }
      }
    }

    return [beforeCumulativeState, afterCumulativeState]
  }, [activeStoreStateEvents, ensureParentPathsExist, workflowStateStart])

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
      const [, after] = accumulateStatePathesToIndex(
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
  }, [
    activeStoreStateEvents,
    activeSetStateEvent,
    beforeActiveSpanStateEvent,
    accumulateStatePathesToIndex,
  ])

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
        {hasFailures && (
          <TabButton tab={DiffTabOptions.FAILURES} activeTab={activeTab} tabChangeHandler={setActiveTab} />
        )}
      </div>
      {/* Failure View */}
      {activeSpan && activeTab === DiffTabOptions.FAILURES && (
        <div className={'grow overflow-y-scroll border-t border-zinc-200 dark:border-zinc-700'}>
          <SpanFailuresList spans={[activeSpan]} />
        </div>
      )}
      {/* Attributes View */}
      {activeSpan && activeTab === DiffTabOptions.SPAN_DETAILS && (
        <div className={'grow overflow-y-scroll border-t border-zinc-200 dark:border-zinc-700 p-4'}>
          <SpanAttributesContent span={activeSpan} origin="workflows" workflowSpanId={defaultWorkflowSpan.span_id} />
        </div>
      )}
      {/* JSON View */}
      {activeTab !== DiffTabOptions.FAILURES && activeTab !== DiffTabOptions.SPAN_DETAILS && (
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

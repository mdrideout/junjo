import { useEffect, useMemo, useRef, useState } from 'react'
import JsonView from '@uiw/react-json-view'
import { lightTheme } from '@uiw/react-json-view/light'
import { vscodeTheme } from '@uiw/react-json-view/vscode'
import { detailedDiff, diff } from 'deep-object-diff'
import { TriangleDownIcon } from '@radix-ui/react-icons'
import { useAppSelector } from '../../../root-store/hooks'
import { RootState } from '../../../root-store/store'
import {
  selectAllWorkflowStateEvents,
  selectSetStateEventsByStoreID,
  selectWorkflowSpanByStoreID,
} from '../../otel/store/selectors'
import * as jsonpatch from 'fast-json-patch'
import { OtelSpan } from '../../otel/store/schemas'
import SpanExceptionsList from './SpanExceptionsList'

enum DiffTabOptions {
  BEFORE = 'Before',
  AFTER = 'After',
  PATCH = 'Patch',
  CHANGES = 'Changes',
  DETAILED = 'Detailed',
  EXCEPTIONS = 'Node Exceptions',
}

interface WorkflowDetailStateDiffProps {
  defaultWorkflowSpan: OtelSpan
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
      {tab}
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
  const serviceName = defaultWorkflowSpan.service_name
  const defaultWorkflowSpanID = defaultWorkflowSpan.span_id

  const openExceptionsTrigger = useAppSelector(
    (state: RootState) => state.workflowDetailState.openExceptionsTrigger,
  )
  const activeSpan = useAppSelector((state: RootState) => state.workflowDetailState.activeSpan)
  const hasExceptions =
    activeSpan?.events_json.some((event) => {
      return event.attributes && event.attributes['exception.type'] !== undefined
    }) ?? false

  const activeSetStateEvent = useAppSelector(
    (state: RootState) => state.workflowDetailState.activeSetStateEvent,
  )

  // Get All Workflow State Events
  // This includes the default top level workflow and all subflows
  const defaultWorkflowSelectorProps = useMemo(
    () => ({
      serviceName,
      workflowSpanID: defaultWorkflowSpanID,
    }),
    [serviceName, defaultWorkflowSpanID],
  )
  const allWorkflowStateEvents = useAppSelector((state: RootState) =>
    selectAllWorkflowStateEvents(state, defaultWorkflowSelectorProps),
  )

  // Active Set State Event - Store ID
  // This is the ID of the store that this state event acted on
  const activeStoreID = activeSetStateEvent?.attributes['junjo.store.id']

  // The active workflow span is the workflow with the same store as the current set state event,
  // defaulting to the default workflow span if there is no active set state event
  // This may be a subflow of the default workflow depending on the set state event
  const activeWorkflowSpan =
    useAppSelector((state: RootState) =>
      selectWorkflowSpanByStoreID(state, { serviceName, storeID: activeStoreID }),
    ) ?? defaultWorkflowSpan

  // Get Active Workflow State Events
  // This is only state events for the currently actively rendering workflow or subflow
  // This is so we can construct the patches of just this rendered JSON state for this workflow and its store
  const activeWorkflowSelectorProps = useMemo(
    () => ({
      serviceName,
      workflowSpanID: defaultWorkflowSpanID,
      storeID: activeStoreID,
    }),
    [serviceName, defaultWorkflowSpanID, activeStoreID],
  )
  const activeWorkflowStateEvents = useAppSelector((state: RootState) =>
    selectSetStateEventsByStoreID(state, activeWorkflowSelectorProps),
  )

  // The structure / starting state of the activeWorkflowSpan
  const renderStateStart = activeWorkflowSpan.junjo_wf_state_start

  // Local State
  const [activeTab, setActiveTab] = useState<DiffTabOptions>(DiffTabOptions.AFTER)
  const [prefersDarkMode, setPrefersDarkMode] = useState<boolean>(false)

  // Workflow JSON States
  // Different representations of the Workflow's states for rendering
  const [beforeJson, setBeforeJson] = useState<object>(renderStateStart)
  const [afterJson, setAfterJson] = useState<object>(renderStateStart)

  // Infer Changes & Detailed tab data using deep-object-diff
  const changesJson = diff(beforeJson, afterJson)
  const detailedJson = detailedDiff(beforeJson, afterJson)

  // All Events Patch Index (for all state events in the parent workflow and subflows)
  const allEventsPatchIndex = allWorkflowStateEvents.findIndex(
    (patch) => patch.attributes.id === activeSetStateEvent?.attributes.id,
  )

  // ActiveWorkflowPatchIndex (for the state events in the active workflow / store)
  const activeWorkflowPatchIndex = activeWorkflowStateEvents.findIndex(
    (patch) => patch.attributes.id === activeSetStateEvent?.attributes.id,
  )

  // The JSON of the current patch
  const currentPatchJson =
    allEventsPatchIndex >= 0
      ? JSON.parse(allWorkflowStateEvents[allEventsPatchIndex].attributes['junjo.state_json_patch'])
      : {}

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

  /**
   * Cumulative Patch Setter
   * Takes the active workflow's starting state, and accumulates the patches to create
   *  - Before: Starting State + Patches up to but excluding the currently selected patch
   *  - After: Starting State + Patches up to and including the currently selected patch
   * @param {number} patchIndex is the index of the currently active patch IN THE active workflow
   * @returns {void} - nothing is returned, this function sets state instead
   */
  const cumulativePatchSetter = (patchIndex: number) => {
    // console.log(
    //   `Running cumulative patch setter for store: ${activeStoreID} and \
    //    patch index: ${patchIndex} / ${activeWorkflowStateEvents.length}`,
    // )

    // If there are no patches, just set the original state
    if (activeWorkflowStateEvents.length === 0) {
      setBeforeJson(renderStateStart)
      setAfterJson(renderStateStart)
      return
    }

    // If the patch index is out of bounds, return
    if (patchIndex < 0 || patchIndex >= activeWorkflowStateEvents.length) return

    // Starting points for accumulating patches
    let beforeCumulativeState = structuredClone(renderStateStart)
    let afterCumulativeState = structuredClone(renderStateStart)

    // Apply patches to the cumulative state
    for (let i = 0; i <= patchIndex; i++) {
      const thisEvent = activeWorkflowStateEvents[i]

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

    // Set state
    setBeforeJson(beforeCumulativeState)
    setAfterJson(afterCumulativeState)
  }

  // Run the patch setter
  useEffect(() => {
    // If activePatchIndex is -1, reset it to the workflow state
    if (activeWorkflowPatchIndex === -1) {
      setBeforeJson(renderStateStart)
      setAfterJson(renderStateStart)
      return
    }

    // Else, use the cumulative state patch setter
    cumulativePatchSetter(activeWorkflowPatchIndex)
  }, [activeWorkflowPatchIndex, activeWorkflowStateEvents])

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
        return currentPatchJson
      default:
        return {}
    }
  }

  return (
    <div className={'flex-1/2 flex flex-col pr-2.5'}>
      <div className={'flex gap-x-2'}>
        <TabButton tab={DiffTabOptions.BEFORE} activeTab={activeTab} tabChangeHandler={setActiveTab} />
        <TabButton tab={DiffTabOptions.AFTER} activeTab={activeTab} tabChangeHandler={setActiveTab} />
        {activeSetStateEvent && (
          <TabButton tab={DiffTabOptions.PATCH} activeTab={activeTab} tabChangeHandler={setActiveTab} />
        )}
        <TabButton tab={DiffTabOptions.CHANGES} activeTab={activeTab} tabChangeHandler={setActiveTab} />
        <TabButton tab={DiffTabOptions.DETAILED} activeTab={activeTab} tabChangeHandler={setActiveTab} />
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
      {/* JSON View */}
      {activeTab !== DiffTabOptions.EXCEPTIONS && (
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

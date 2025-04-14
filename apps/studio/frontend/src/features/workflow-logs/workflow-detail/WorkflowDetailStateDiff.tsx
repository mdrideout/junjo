import { useEffect, useMemo, useState } from 'react'
import JsonView from '@uiw/react-json-view'
import { lightTheme } from '@uiw/react-json-view/light'
import { vscodeTheme } from '@uiw/react-json-view/vscode'
import { detailedDiff, diff } from 'deep-object-diff'
import { TriangleDownIcon } from '@radix-ui/react-icons'
import { useActiveNodeContext } from './ActiveNodeContext'
import { useAppSelector } from '../../../root-store/hooks'
import { RootState } from '../../../root-store/store'
import { selectAllWorkflowStateEvents } from '../../otel/store/selectors'
import * as jsonpatch from 'fast-json-patch'
import WorkflowStateEventNavButtons from './WorkflowStateDiffNavButtons'
import { formatMicrosecondsSinceEpochToTime } from '../../../util/duration-utils'

enum DiffTabOptions {
  BEFORE = 'Before',
  AFTER = 'After',
  PATCH = 'Patch',
  CHANGES = 'Changes',
  DETAILED = 'Detailed',
}

interface WorkflowDetailStateDiffProps {
  workflowStateStart: Record<string, any>
  workflowStateEnd: Record<string, any>
  serviceName: string
  workflowSpanID: string
}

/**
 * Abstracted Button
 * @param tab
 * @param activeTab
 * @param tabChangeHandler
 * @returns
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
  const { workflowStateStart, workflowStateEnd, serviceName, workflowSpanID } = props
  const { activeSetStateEvent } = useActiveNodeContext()

  // Local State
  const [activeTab, setActiveTab] = useState<DiffTabOptions>(DiffTabOptions.AFTER)
  const [prefersDarkMode, setPrefersDarkMode] = useState<boolean>(false)

  // Workflow JSON States
  // Different representations of the Workflow's states for rendering
  const [beforeJson, setBeforeJson] = useState<object>(workflowStateStart)
  const [afterJson, setAfterJson] = useState<object>(workflowStateEnd)

  // Infer Changes & Detailed tab data using deep-object-diff
  const changesJson = diff(beforeJson, afterJson)
  const detailedJson = detailedDiff(beforeJson, afterJson)

  // Selectors
  // Memoize the props object
  const selectorProps = useMemo(
    () => ({
      serviceName,
      workflowSpanID,
    }),
    [serviceName, workflowSpanID],
  )

  // Use the memoized props object
  const workflowStateEvents = useAppSelector((state: RootState) =>
    selectAllWorkflowStateEvents(state, selectorProps),
  )

  // Active Patch Isolation
  const activePatchIndex = workflowStateEvents.findIndex(
    (patch) => patch.attributes.id === activeSetStateEvent?.attributes.id,
  )
  const activePatchJson =
    activePatchIndex >= 0
      ? JSON.parse(workflowStateEvents[activePatchIndex].attributes['junjo.state_json_patch'])
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

  /**
   * Cumulative Patch Setter
   * Takes the workflow's starting state, and accumulates the patches to create
   *  - Before: Starting State + Patches up to but excluding the currently selected patch
   *  - After: Starting State + Patches up to and including the currently selected patch
   * @param {number} patchIndex is the index of the currently active patch
   * @returns {void} - nothing is returned, this function sets state instead
   */
  const cumulativePatchSetter = (patchIndex: number) => {
    console.log('Running cumulative patch setter.')

    // If there are no patches, just set the original state
    if (workflowStateEvents.length === 0) {
      setBeforeJson(workflowStateStart)
      setAfterJson(workflowStateEnd)
      return
    }

    // If the patch index is out of bounds, return
    if (patchIndex < 0 || patchIndex >= workflowStateEvents.length) return

    // Starting points for accumulating patches
    let beforeCumulativeState = structuredClone(workflowStateStart)
    let afterCumulativeState = structuredClone(workflowStateStart)
    console.log('Before cumulative state: ', beforeCumulativeState)
    console.log('After cumulative state: ', afterCumulativeState)

    // Apply patches to the cumulative state
    for (let i = 0; i <= patchIndex; i++) {
      const thisEvent = workflowStateEvents[i]
      console.log('Adding patch from this state event: ', thisEvent)

      const patchString = thisEvent.attributes['junjo.state_json_patch']
      const patch = JSON.parse(patchString)
      console.log(`Patch ${i} of ${patchIndex}`)
      console.log('Patch string: ', patchString)
      console.log('Patch: ', patch)

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
    if (activePatchIndex === -1) {
      setBeforeJson(workflowStateStart)
      setAfterJson(workflowStateEnd)
      return
    }

    // Else, use the cumulative state patch setter
    cumulativePatchSetter(activePatchIndex)
  }, [activePatchIndex, workflowStateEvents])

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
        return activePatchJson
      default:
        return {}
    }
  }

  const statePatchTime = activeSetStateEvent?.timeUnixNano
  const start_micro = statePatchTime
    ? formatMicrosecondsSinceEpochToTime(activeSetStateEvent?.timeUnixNano / 1000)
    : null

  return (
    <div className={'flex-1 overflow-y-scroll pr-2.5'}>
      {activeSetStateEvent && (
        <div
          className={
            'flex justify-between items-center text-xs mb-2 border-b border-zinc-300 px-2 pb-2 font-bold'
          }
        >
          <div>Patch: {activeSetStateEvent?.attributes.id}</div>
          <div className={'flex items-center gap-x-2'}>
            {' '}
            {start_micro} &mdash; ({activePatchIndex + 1}/{workflowStateEvents.length})
            <WorkflowStateEventNavButtons workflowStateEvents={workflowStateEvents} />
          </div>
        </div>
      )}
      <div className={'flex gap-x-2 mb-2'}>
        <TabButton tab={DiffTabOptions.BEFORE} activeTab={activeTab} tabChangeHandler={setActiveTab} />
        <TabButton tab={DiffTabOptions.AFTER} activeTab={activeTab} tabChangeHandler={setActiveTab} />
        {activeSetStateEvent && (
          <TabButton tab={DiffTabOptions.PATCH} activeTab={activeTab} tabChangeHandler={setActiveTab} />
        )}
        <TabButton tab={DiffTabOptions.CHANGES} activeTab={activeTab} tabChangeHandler={setActiveTab} />
        <TabButton tab={DiffTabOptions.DETAILED} activeTab={activeTab} tabChangeHandler={setActiveTab} />
      </div>
      <div className={'workflow-logs-json-container'}>
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
          style={displayTheme}
        >
          {/* Zero width whitespace char */}
          <JsonView.Quote>&#8203;</JsonView.Quote>
          <JsonView.Arrow>
            <TriangleDownIcon className={'size-4 leading-0'} />
          </JsonView.Arrow>
        </JsonView>
      </div>
    </div>
  )
}

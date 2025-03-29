import { useEffect, useState } from 'react'
import JsonView from '@uiw/react-json-view'
import { lightTheme } from '@uiw/react-json-view/light'
import { vscodeTheme } from '@uiw/react-json-view/vscode'
import { detailedDiff, diff } from 'deep-object-diff'
import { TriangleDownIcon } from '@radix-ui/react-icons'
import { useActiveNodeContext } from './ActiveNodeContext'
import { useAppSelector } from '../../../root-store/hooks'
import { RootState } from '../../../root-store/store'
import { selectAllWorkflowStateEvents } from '../../otel/store/selectors'

enum DiffTabOptions {
  BEFORE = 'Before',
  AFTER = 'After',
  PATCH = 'Patch',
  CHANGES = 'Changes',
  DETAILED = 'Detailed',
}

interface WorkflowDetailStateDiffProps {
  stateStart: Record<string, any>
  stateEnd: Record<string, any>
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
  const { stateStart, stateEnd, serviceName, workflowSpanID } = props
  const { activeStatePatch } = useActiveNodeContext()

  // Local State
  const [activeTab, setActiveTab] = useState<DiffTabOptions>(DiffTabOptions.AFTER)
  const [jsonViewData, setJsonViewData] = useState<object>(stateEnd)
  const [jsonViewCollapsedLevel, setJsonViewCollapsedLevel] = useState<number>(2)
  const [prefersDarkMode, setPrefersDarkMode] = useState<boolean>(false)

  // Selectors
  const workflowPatches = useAppSelector((state: RootState) =>
    selectAllWorkflowStateEvents(state, {
      serviceName,
      workflowSpanID,
    }),
  )
  console.log('Workflow Patches: ', workflowPatches)

  // Get index of activeStatePatch in the workflowPatches array
  const activePatchIndex = workflowPatches.findIndex((patch) => patch.attributes.id === activeStatePatch?.patchID)
  console.log('Active patch index: ', activePatchIndex)

  // Diffs
  const objdiff = diff(stateStart, stateEnd)
  const deepObject = detailedDiff(stateStart, stateEnd)

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

  // Handle tab changes
  const tabChangeHandler = (tab: DiffTabOptions) => {
    setActiveTab(tab)

    // Set the display values
    switch (tab) {
      case DiffTabOptions.BEFORE:
        setJsonViewData(stateStart)
        setJsonViewCollapsedLevel(2)
        break
      case DiffTabOptions.AFTER:
        setJsonViewData(stateEnd)
        setJsonViewCollapsedLevel(2)
        break
      case DiffTabOptions.CHANGES:
        setJsonViewData(objdiff)
        setJsonViewCollapsedLevel(1)
        break
      case DiffTabOptions.DETAILED:
        setJsonViewData(deepObject)
        setJsonViewCollapsedLevel(2)
        break
      default:
        break
    }
  }

  return (
    <div className={'grow'}>
      <div>
        TODO: Update this to select all patches for this workflow, and allow forward / backward stepping. Left side
        selection of a specific state update will control this side's nav.
      </div>
      <div className={'flex gap-x-2'}>
        {workflowPatches.length > 0 &&
          workflowPatches.map((patch) => {
            const isActive = activeStatePatch?.patchID === patch.attributes.id
            return (
              <div
                className={`bg-amber-100 text-zinc-900 rounded-md px-2 cursor-pointer text-xs ${isActive ? 'bg-amber-100' : 'bg-amber-300'}`}
              >
                {patch.attributes.id}
              </div>
            )
          })}
      </div>
      <div className={'flex gap-x-2 mb-2'}>
        <TabButton tab={DiffTabOptions.BEFORE} activeTab={activeTab} tabChangeHandler={tabChangeHandler} />
        <TabButton tab={DiffTabOptions.AFTER} activeTab={activeTab} tabChangeHandler={tabChangeHandler} />
        {activeStatePatch && (
          <TabButton tab={DiffTabOptions.PATCH} activeTab={activeTab} tabChangeHandler={tabChangeHandler} />
        )}
        <TabButton tab={DiffTabOptions.CHANGES} activeTab={activeTab} tabChangeHandler={tabChangeHandler} />
        <TabButton tab={DiffTabOptions.DETAILED} activeTab={activeTab} tabChangeHandler={tabChangeHandler} />
      </div>
      <div className={'workflow-logs-json-container'}>
        <JsonView
          key={JSON.stringify(jsonViewData)}
          value={jsonViewData}
          collapsed={jsonViewCollapsedLevel}
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

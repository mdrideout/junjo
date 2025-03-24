import { useEffect, useState } from 'react'
import JsonView from '@uiw/react-json-view'
import { lightTheme } from '@uiw/react-json-view/light'
import { vscodeTheme } from '@uiw/react-json-view/vscode'
import { detailedDiff, diff } from 'deep-object-diff'
import { TriangleDownIcon } from '@radix-ui/react-icons'
import { useActiveNodeContext } from './ActiveNodeContext'

enum DiffTabOptions {
  BEFORE = 'Before',
  AFTER = 'After',
  CHANGES = 'Changes',
  DETAILED = 'Detailed',
}

interface WorkflowDetailStateDiffProps {
  stateStart: Record<string, any>
  stateEnd: Record<string, any>
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
  const getButtonClass = () => {
    return `leading-tight px-2 py-1 hover:bg-zinc-100 dark:hover:bg-zinc-700 text-sm font-medium border-b transition-all duration-200 cursor-pointer ${activeTab === tab ? 'border-zinc-600 ' : 'border-transparent'}`
  }
  return (
    <button className={getButtonClass()} onClick={() => tabChangeHandler(tab)}>
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
  const { stateStart, stateEnd } = props
  const { activeStatePatch } = useActiveNodeContext()

  // Local State
  const [activeTab, setActiveTab] = useState<DiffTabOptions>(DiffTabOptions.AFTER)
  const [jsonViewData, setJsonViewData] = useState<object>(stateEnd)
  const [jsonViewCollapsedLevel, setJsonViewCollapsedLevel] = useState<number>(2)
  const [prefersDarkMode, setPrefersDarkMode] = useState<boolean>(false)

  // Diffs
  const objdiff = diff(stateStart, stateEnd)
  const deepObject = detailedDiff(stateStart, stateEnd)

  // Theme decider
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

  // Set the initial json view
  useEffect

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
      <div>Active Patch: {activeStatePatch?.patchID}</div>
      <div className={'flex gap-x-2'}>
        <div className={'bg-amber-100 rounded-md px-2 cursor-pointer'}>patch 1</div>
        <div className={'bg-amber-100 rounded-md px-2 cursor-pointer'}>patch 2</div>
        <div className={'bg-amber-100 rounded-md px-2 cursor-pointer'}>patch 3</div>
        <div className={'bg-amber-100 rounded-md px-2 cursor-pointer'}>patch etc.</div>
      </div>
      <div className={'flex gap-x-2 mb-2'}>
        <TabButton tab={DiffTabOptions.BEFORE} activeTab={activeTab} tabChangeHandler={tabChangeHandler} />
        <TabButton tab={DiffTabOptions.AFTER} activeTab={activeTab} tabChangeHandler={tabChangeHandler} />
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

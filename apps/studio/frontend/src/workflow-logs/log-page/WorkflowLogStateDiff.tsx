import { useEffect, useState } from 'react'
import JsonView from '@uiw/react-json-view'
import { lightTheme } from '@uiw/react-json-view/light'
import { vscodeTheme } from '@uiw/react-json-view/vscode'
import { detailedDiff, diff } from 'deep-object-diff'
import { TriangleDownIcon } from '@radix-ui/react-icons'

enum DiffTabOptions {
  BEFORE = 'Before',
  AFTER = 'After',
  CHANGES = 'Changes',
  DETAILED = 'Detailed',
}

interface WorkflowLogStateDiffProps {
  jsonLogs0: object
  jsonLogs1: object
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
    return `leading-tight px-2 py-1 hover:bg-zinc-100 text-sm font-medium border-b transition-all duration-200 ${activeTab === tab ? 'border-zinc-600 ' : 'border-transparent'}`
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
export default function WorkflowLogStateDiff(props: WorkflowLogStateDiffProps) {
  const { jsonLogs0, jsonLogs1 } = props
  const [activeTab, setActiveTab] = useState<DiffTabOptions>(DiffTabOptions.AFTER)
  const [jsonViewData, setJsonViewData] = useState<object>(jsonLogs0)
  const [jsonViewCollapsedLevel, setJsonViewCollapsedLevel] = useState<number>(1)
  const [prefersDarkMode, setPrefersDarkMode] = useState<boolean>(false)

  // Diffs
  const objdiff = diff(jsonLogs0, jsonLogs1)
  const deepObject = detailedDiff(jsonLogs0, jsonLogs1)

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

  // Handle tab changes
  const tabChangeHandler = (tab: DiffTabOptions) => {
    setActiveTab(tab)

    // Set the display values
    switch (tab) {
      case DiffTabOptions.BEFORE:
        setJsonViewData(jsonLogs0)
        setJsonViewCollapsedLevel(1)
        break
      case DiffTabOptions.AFTER:
        setJsonViewData(jsonLogs1)
        setJsonViewCollapsedLevel(1)
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
    <div>
      <div className={'flex gap-x-2 mb-2'}>
        <TabButton tab={DiffTabOptions.BEFORE} activeTab={activeTab} tabChangeHandler={tabChangeHandler} />
        <TabButton tab={DiffTabOptions.AFTER} activeTab={activeTab} tabChangeHandler={tabChangeHandler} />
        <TabButton tab={DiffTabOptions.CHANGES} activeTab={activeTab} tabChangeHandler={tabChangeHandler} />
        <TabButton tab={DiffTabOptions.DETAILED} activeTab={activeTab} tabChangeHandler={tabChangeHandler} />
      </div>
      <div className={'workflow-logs-json-container'}>
        <JsonView
          value={jsonViewData}
          collapsed={jsonViewCollapsedLevel}
          shouldExpandNodeInitially={(isExpanded, { value, keys, level }) => {
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
          <JsonView.Quote>&#8203;</JsonView.Quote>
          <JsonView.Arrow>
            <TriangleDownIcon className={'size-4 leading-0'} />
          </JsonView.Arrow>
        </JsonView>
      </div>
    </div>
  )
}

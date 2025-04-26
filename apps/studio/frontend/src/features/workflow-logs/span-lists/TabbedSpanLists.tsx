import { useState } from 'react'
import NestedWorkflowSpans from './NestedWorkflowSpans'
import FlatStateEventsList from './FlatStateEventsList'

enum TabOptions {
  NESTED = 'Nested Spans',
  FLAT = 'State Updates',
}

interface TabbedSpanListsProps {
  serviceName: string
  workflowSpanID: string
}

/**
 * Abstracted Button
 */
const TabButton = ({
  tab,
  activeTab,
  tabChangeHandler,
}: {
  tab: TabOptions
  activeTab: TabOptions
  tabChangeHandler: (tab: TabOptions) => void
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

export default function TabbedSpanLists(props: TabbedSpanListsProps) {
  const { serviceName, workflowSpanID } = props
  const [activeTab, setActiveTab] = useState<TabOptions>(TabOptions.NESTED)

  return (
    <div className={'flex flex-1/2 flex-col'}>
      <div className={'flex gap-x-2 mb-2'}>
        <TabButton tab={TabOptions.NESTED} activeTab={activeTab} tabChangeHandler={setActiveTab} />
        <TabButton tab={TabOptions.FLAT} activeTab={activeTab} tabChangeHandler={setActiveTab} />
      </div>
      <div className={'overflow-y-scroll pr-2.5'}>
        {activeTab === TabOptions.FLAT && (
          <FlatStateEventsList serviceName={serviceName} workflowSpanID={workflowSpanID} />
        )}
        {activeTab === TabOptions.NESTED && (
          <NestedWorkflowSpans serviceName={serviceName} workflowSpanID={workflowSpanID} />
        )}
      </div>
    </div>
  )
}

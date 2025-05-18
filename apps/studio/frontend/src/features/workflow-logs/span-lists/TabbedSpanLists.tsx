import { useMemo, useState } from 'react'
import NestedWorkflowSpans from './NestedWorkflowSpans'
import FlatStateEventsList from './FlatStateEventsList'
import { useAppSelector } from '../../../root-store/hooks'
import { RootState } from '../../../root-store/store'
import { selectAllExceptionSpans } from '../../otel/store/selectors'
import SpanExceptionsList from '../workflow-detail/SpanExceptionsList'
import { ExclamationTriangleIcon } from '@heroicons/react/24/solid'

enum TabOptions {
  NESTED = 'Nested Spans',
  FLAT = 'State Updates',
  EXCEPTIONS = 'Workflow Exceptions',
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
      <div className={'flex items-center gap-x-1'}>
        {tab === TabOptions.EXCEPTIONS && <ExclamationTriangleIcon className={'size-5 text-red-700'} />}
        <div>{tab}</div>
      </div>
    </button>
  )
}

export default function TabbedSpanLists(props: TabbedSpanListsProps) {
  const { serviceName, workflowSpanID } = props
  const [activeTab, setActiveTab] = useState<TabOptions>(TabOptions.NESTED)

  const selectorProps = useMemo(
    () => ({
      serviceName,
      spanID: workflowSpanID,
    }),
    [serviceName, workflowSpanID],
  )

  const exceptionSpans = useAppSelector((state: RootState) => selectAllExceptionSpans(state, selectorProps))
  const hasExceptions = exceptionSpans.length > 0

  return (
    <div className={'flex flex-1/2 flex-col'}>
      <div className={'flex gap-x-2'}>
        <TabButton tab={TabOptions.NESTED} activeTab={activeTab} tabChangeHandler={setActiveTab} />
        <TabButton tab={TabOptions.FLAT} activeTab={activeTab} tabChangeHandler={setActiveTab} />
        {hasExceptions && (
          <TabButton tab={TabOptions.EXCEPTIONS} activeTab={activeTab} tabChangeHandler={setActiveTab} />
        )}
      </div>
      <div className={'overflow-y-scroll pr-2.5 border-t border-zinc-200 dark:border-zinc-700'}>
        {activeTab === TabOptions.FLAT && (
          <FlatStateEventsList serviceName={serviceName} workflowSpanID={workflowSpanID} />
        )}
        {activeTab === TabOptions.NESTED && (
          <NestedWorkflowSpans serviceName={serviceName} workflowSpanID={workflowSpanID} />
        )}
        {activeTab === TabOptions.EXCEPTIONS && <SpanExceptionsList spans={exceptionSpans} />}
      </div>
    </div>
  )
}

import { useState } from 'react'
import NestedWorkflowSpans from './NestedWorkflowSpans'
import FlatStateEventsList from './FlatStateEventsList'
import { ExclamationTriangleIcon } from '@heroicons/react/24/solid'
import { selectTraceFailureSpans } from '../../traces/store/selectors'
import { useAppSelector } from '../../../root-store/hooks'
import { RootState } from '../../../root-store/store'
import SpanFailuresList from '../workflow-detail/SpanFailuresList'
import type { WorkflowStoreDiagnosticRequest } from '../../workflow-executions/hooks/use-workflow-store-diagnostic'

enum TabOptions {
  NESTED = 'Workflow Spans',
  FLAT = 'State Updates',
  FAILURES = 'Workflow Failures',
}

interface TabbedSpanListsProps {
  traceId: string
  workflowSpanId: string
  storeDiagnosticRequest: WorkflowStoreDiagnosticRequest
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
        {tab === TabOptions.FAILURES && <ExclamationTriangleIcon className={'size-4 text-red-700'} />}
        <div>{tab}</div>
      </div>
    </button>
  )
}

export default function TabbedSpanLists(props: TabbedSpanListsProps) {
  const { traceId, workflowSpanId, storeDiagnosticRequest } = props
  const [activeTab, setActiveTab] = useState<TabOptions>(TabOptions.NESTED)

  const failureSpans = useAppSelector((state: RootState) =>
    selectTraceFailureSpans(state, {
      traceId,
    }),
  )
  const hasFailures = failureSpans.length > 0

  return (
    <div className={'flex flex-1/2 flex-col'}>
      <div className={'flex gap-x-2'}>
        <TabButton tab={TabOptions.NESTED} activeTab={activeTab} tabChangeHandler={setActiveTab} />
        <TabButton tab={TabOptions.FLAT} activeTab={activeTab} tabChangeHandler={setActiveTab} />
        {hasFailures && (
          <TabButton tab={TabOptions.FAILURES} activeTab={activeTab} tabChangeHandler={setActiveTab} />
        )}
      </div>
      <div className={'overflow-y-scroll pr-2.5 border-t border-zinc-200 dark:border-zinc-700'}>
        {activeTab === TabOptions.NESTED && (
          <NestedWorkflowSpans traceId={traceId} workflowSpanId={workflowSpanId} />
        )}
        {activeTab === TabOptions.FLAT && (
          <FlatStateEventsList
            traceId={traceId}
            workflowSpanId={workflowSpanId}
            storeDiagnosticRequest={storeDiagnosticRequest}
          />
        )}
        {activeTab === TabOptions.FAILURES && <SpanFailuresList spans={failureSpans} />}
      </div>
    </div>
  )
}

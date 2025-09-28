import { useAppDispatch, useAppSelector } from '../../../root-store/hooks'
import { useEffect } from 'react'
import { WorkflowExecutionsStateActions } from './store/slice'
import WorkflowListRow from './WorkflowListItem'

export default function WorkflowsList() {
  const dispatch = useAppDispatch()

  const loading = useAppSelector((state) => state.workflowSpanListState.loading)
  const error = useAppSelector((state) => state.workflowSpanListState.error)
  const workflowSpans = useAppSelector((state) => state.workflowSpanListState.workflowSpanList)

  useEffect(() => {
    dispatch(WorkflowExecutionsStateActions.fetchSpansTypeWorkflow())
  }, [dispatch])

  if (loading) {
    return <div>Loading...</div>
  }

  if (error) {
    return <div>Error loading workflow executions.</div>
  }

  return (
    <table className="text-left text-sm">
      <thead>
        <tr>
          <th className={'px-4 py-1'}>Workflow</th>
          <th className={'px-4 py-1'}>Trace ID</th>
          <th className={'px-4 py-1'}>Span ID</th>
          <th className={'px-4 py-1'}>Start Time</th>
          <th className={'px-4 py-1'}>Nodes</th>
          <th className={'px-4 py-1'}>Duration</th>
          <th className={'px-4 py-1'}>Exception</th>
        </tr>
      </thead>
      <tbody>
        {workflowSpans.map((item) => (
          <WorkflowListRow key={`list-row-${item.span_id}`} workflowSpan={item} />
        ))}
      </tbody>
    </table>
  )
}

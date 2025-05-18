import { useNavigate } from 'react-router'
import { ExclamationTriangleIcon } from '@heroicons/react/24/solid'
import { getSpanDurationString } from '../../../util/duration-utils'
import { OtelSpan } from '../../otel/store/schemas'
import { useAppDispatch, useAppSelector } from '../../../root-store/hooks'
import { RootState } from '../../../root-store/store'
import { workflowExecutionRequestHasExceptions } from '../../otel/store/selectors'
import { useMemo } from 'react'
import { WorkflowDetailStateActions } from '../workflow-detail/store/slice'

// Define the shape of one span; replace `any` with your real type if you have one
interface Props {
  workflowSpan: OtelSpan
}

export default function WorkflowListRow({ workflowSpan }: Props) {
  const navigate = useNavigate()
  const dispatch = useAppDispatch()

  const nodeCount = workflowSpan.attributes_json['junjo.workflow.node.count'] ?? null
  const startString = new Date(workflowSpan.start_time).toLocaleString()
  const durationString = getSpanDurationString(workflowSpan.start_time, workflowSpan.end_time)

  // Memoize the props object for the selector
  const selectorProps = useMemo(
    () => ({
      serviceName: workflowSpan.service_name,
      spanID: workflowSpan.span_id,
    }),
    [workflowSpan.service_name, workflowSpan.span_id],
  )

  // Check if there are any exceptions in the events_json
  const hasExceptions = useAppSelector((state: RootState) =>
    workflowExecutionRequestHasExceptions(state, selectorProps),
  )

  return (
    <tr
      key={workflowSpan.span_id}
      className={
        'last-of-type:border-0 border-b border-zinc-200 dark:border-zinc-600 hover:bg-zinc-200 dark:hover:bg-zinc-700 cursor-pointer'
      }
      onClick={() => {
        // Clear the activeSpan
        dispatch(WorkflowDetailStateActions.setActiveSpan(null))

        // Navigate
        navigate(`${workflowSpan.span_id}`)
      }}
    >
      <td className="px-4 py-1.5">{workflowSpan.name}</td>
      <td className="px-4 py-1.5 font-mono">{workflowSpan.span_id}</td>
      <td className="px-4 py-1.5 font-mono">{startString}</td>
      <td className="px-4 py-1.5 text-right font-mono">{nodeCount}</td>
      <td className="px-4 py-1.5 text-right font-mono">{durationString}</td>
      <td className="px-4 py-1.5">
        {hasExceptions && (
          <ExclamationTriangleIcon className="size-5 m-auto text-red-700 dark:text-red-300" />
        )}
      </td>
    </tr>
  )
}

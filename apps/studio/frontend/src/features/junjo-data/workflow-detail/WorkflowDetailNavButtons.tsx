import { ArrowDownIcon, ArrowUpIcon } from '@radix-ui/react-icons'
import { useNavigate } from 'react-router'
import { useAppDispatch, useAppSelector } from '../../../root-store/hooks'
import { RootState } from '../../../root-store/store'
import { WorkflowDetailStateActions } from './store/slice'
import { selectNextWorkflowSpan, selectPrevWorkflowSpan } from '../list-spans-workflow/store/selectors'
import { useEffect } from 'react'
import { WorkflowExecutionsStateActions } from '../list-spans-workflow/store/slice'

interface WorkflowDetailNavButtonsProps {
  serviceName: string
  workflowSpanId: string
}

export default function WorkflowDetailNavButtons(props: WorkflowDetailNavButtonsProps) {
  const { serviceName, workflowSpanId } = props
  const navigate = useNavigate()
  const dispatch = useAppDispatch()

  useEffect(() => {
    dispatch(WorkflowExecutionsStateActions.fetchSpansTypeWorkflow(serviceName))
  }, [dispatch, serviceName])

  const prevWorkflowSpan = useAppSelector((state: RootState) =>
    selectPrevWorkflowSpan(state, { serviceName, spanID: workflowSpanId }),
  )
  const nextWorkflowSpan = useAppSelector((state: RootState) =>
    selectNextWorkflowSpan(state, { serviceName, spanID: workflowSpanId }),
  )

  const disablePrev = prevWorkflowSpan === undefined
  const disableNext = nextWorkflowSpan === undefined

  const handlePrevClick = () => {
    if (!disablePrev) {
      // Clear the activeSpan
      dispatch(WorkflowDetailStateActions.setActiveSpan(null))
      dispatch(WorkflowDetailStateActions.setActiveSetStateEvent(null))

      // Navigate
      navigate(
        `/workflows/${prevWorkflowSpan.service_name}/${prevWorkflowSpan.trace_id}/${prevWorkflowSpan.span_id}`,
      )
    }
  }

  const handleNextClick = () => {
    if (!disableNext) {
      // Clear the activeSpan
      dispatch(WorkflowDetailStateActions.setActiveSpan(null))
      dispatch(WorkflowDetailStateActions.setActiveSetStateEvent(null))

      // Navigate
      navigate(
        `/workflows/${nextWorkflowSpan.service_name}/${nextWorkflowSpan.trace_id}/${nextWorkflowSpan.span_id}`,
      )
    }
  }

  return (
    <div className={'flex flex-col gap-y-1'}>
      <button
        className={
          'border border-zinc-300 rounded-md p-[0px] hover:bg-zinc-300 cursor-pointer disabled:opacity-20'
        }
        onClick={handlePrevClick}
        disabled={disablePrev}
      >
        <ArrowUpIcon />
      </button>

      <button
        className={
          'border border-zinc-300 rounded-md p-[0px] hover:bg-zinc-300 cursor-pointer disabled:opacity-20'
        }
        onClick={handleNextClick}
        disabled={disableNext}
      >
        <ArrowDownIcon />
      </button>
    </div>
  )
}

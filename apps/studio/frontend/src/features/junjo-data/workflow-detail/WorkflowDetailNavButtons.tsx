import { ArrowDownIcon, ArrowUpIcon } from '@radix-ui/react-icons'
import { useNavigate } from 'react-router'
import { useAppDispatch, useAppSelector } from '../../../root-store/hooks'
import { RootState } from '../../../root-store/store'
import { selectNextWorkflowSpanID, selectPrevWorkflowSpanID } from './store/selectors'
import { WorkflowDetailStateActions } from './store/slice'

interface WorkflowDetailNavButtonsProps {
  serviceName: string
  workflowSpanID: string
}

export default function WorkflowDetailNavButtons(props: WorkflowDetailNavButtonsProps) {
  const { serviceName, workflowSpanID } = props
  const navigate = useNavigate()
  const dispatch = useAppDispatch()

  const prevSpanID = useAppSelector((state: RootState) =>
    selectPrevWorkflowSpanID(state, { serviceName, spanID: workflowSpanID }),
  )
  const nextSpanID = useAppSelector((state: RootState) =>
    selectNextWorkflowSpanID(state, { serviceName, spanID: workflowSpanID }),
  )

  const disablePrev = prevSpanID === undefined
  const disableNext = nextSpanID === undefined

  const handlePrevClick = () => {
    if (!disablePrev) {
      // Clear the activeSpan
      dispatch(WorkflowDetailStateActions.setActiveSpan(null))
      dispatch(WorkflowDetailStateActions.setActiveSetStateEvent(null))

      // Navigate
      navigate(`/logs/${serviceName}/${prevSpanID}`)
    }
  }

  const handleNextClick = () => {
    if (!disableNext) {
      // Clear the activeSpan
      dispatch(WorkflowDetailStateActions.setActiveSpan(null))
      dispatch(WorkflowDetailStateActions.setActiveSetStateEvent(null))

      // Navigate
      navigate(`/logs/${serviceName}/${nextSpanID}`)
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

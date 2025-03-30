import { ArrowDownIcon, ArrowUpIcon } from '@radix-ui/react-icons'
import { useNavigate } from 'react-router'
import { useAppSelector } from '../../../root-store/hooks'
import { RootState } from '../../../root-store/store'
import { selectNextWorkflowSpanID, selectPrevWorkflowSpanID } from '../../otel/store/selectors'

interface WorkflowDetailNavButtonsProps {
  serviceName: string
  workflowSpanID: string
}

export default function WorkflowDetailNavButtons(props: WorkflowDetailNavButtonsProps) {
  const { serviceName, workflowSpanID } = props
  const navigate = useNavigate()

  const prevSpanID = useAppSelector((state: RootState) =>
    selectPrevWorkflowSpanID(state, { serviceName, workflowSpanID }),
  )
  const nextSpanID = useAppSelector((state: RootState) =>
    selectNextWorkflowSpanID(state, { serviceName, workflowSpanID }),
  )

  const disablePrev = prevSpanID === undefined
  const disableNext = nextSpanID === undefined

  const handlePrevClick = () => {
    if (!disablePrev) {
      navigate(`/logs/${serviceName}/${prevSpanID}`)
    }
  }

  const handleNextClick = () => {
    if (!disableNext) {
      navigate(`/logs/${serviceName}/${nextSpanID}`)
    }
  }

  return (
    <div className={'flex flex-col gap-y-1'}>
      <button
        className={'border border-zinc-300 rounded-md p-[0px] hover:bg-zinc-300 cursor-pointer disabled:opacity-20'}
        onClick={handlePrevClick}
        disabled={disablePrev}
      >
        <ArrowUpIcon />
      </button>

      <button
        className={'border border-zinc-300 rounded-md p-[0px] hover:bg-zinc-300 cursor-pointer disabled:opacity-20'}
        onClick={handleNextClick}
        disabled={disableNext}
      >
        <ArrowDownIcon />
      </button>
    </div>
  )
}

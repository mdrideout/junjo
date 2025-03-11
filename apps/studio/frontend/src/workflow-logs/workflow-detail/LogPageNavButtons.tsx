import { ArrowDownIcon, ArrowUpIcon } from '@radix-ui/react-icons'
import { useQuery } from '@tanstack/react-query'
import { useNavigate, useParams } from 'react-router'
import { WorkflowMetadatum } from '../schemas'
import { fetchWorkflowMetadataList } from '../fetch/fetch-workflow-metadata'

interface LogPageNavButtonsProps {
  ExecID: string
}

export default function LogPageNavButtons(props: LogPageNavButtonsProps) {
  const { ExecID } = props
  const { AppName } = useParams()
  const navigate = useNavigate()

  const {
    data: metadataList,
    isLoading,
    isError,
    error,
  } = useQuery<WorkflowMetadatum[], Error>({
    queryKey: ['workflowMetadataList', AppName],
    enabled: !!AppName,
    queryFn: () => fetchWorkflowMetadataList(AppName!),
    select: (data) => data,
    // refetchInterval: 1000 * 3,
  })

  if (isLoading || isError || error || !metadataList) {
    return null
  }

  const thisExecIDIndex = metadataList.findIndex((item) => item.ExecID === ExecID)
  const disablePrev = thisExecIDIndex === 0
  const disableNext = thisExecIDIndex === metadataList.length - 1

  const handlePrevClick = () => {
    if (!disablePrev) {
      const prevExecID = metadataList[thisExecIDIndex - 1].ExecID
      navigate(`/logs/${AppName}/${prevExecID}`)
    }
  }

  const handleNextClick = () => {
    if (!disableNext) {
      const nextExecID = metadataList[thisExecIDIndex + 1].ExecID
      navigate(`/logs/${AppName}/${nextExecID}`)
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

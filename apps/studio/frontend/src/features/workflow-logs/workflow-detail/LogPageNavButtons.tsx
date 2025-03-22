interface LogPageNavButtonsProps {
  ExecID: string
}

export default function LogPageNavButtons(props: LogPageNavButtonsProps) {
  const { ExecID } = props
  // const { AppName } = useParams()
  // const navigate = useNavigate()

  const loading = false
  const error = false

  if (loading || error) {
    return null
  }

  console.log('ExecID NAV: ', ExecID)
  return <div>NAV</div>

  // const thisExecIDIndex = workflowExecutions.findIndex((item) => item.ExecID === ExecID)
  // const disablePrev = thisExecIDIndex === 0
  // const disableNext = thisExecIDIndex === workflowExecutions.length - 1

  // const handlePrevClick = () => {
  //   if (!disablePrev) {
  //     const prevExecID = workflowExecutions[thisExecIDIndex - 1].ExecID
  //     navigate(`/logs/${AppName}/${prevExecID}`)
  //   }
  // }

  // const handleNextClick = () => {
  //   if (!disableNext) {
  //     const nextExecID = workflowExecutions[thisExecIDIndex + 1].ExecID
  //     navigate(`/logs/${AppName}/${nextExecID}`)
  //   }
  // }

  // return (
  //   <div className={'flex flex-col gap-y-1'}>
  //     <button
  //       className={'border border-zinc-300 rounded-md p-[0px] hover:bg-zinc-300 cursor-pointer disabled:opacity-20'}
  //       onClick={handlePrevClick}
  //       disabled={disablePrev}
  //     >
  //       <ArrowUpIcon />
  //     </button>

  //     <button
  //       className={'border border-zinc-300 rounded-md p-[0px] hover:bg-zinc-300 cursor-pointer disabled:opacity-20'}
  //       onClick={handleNextClick}
  //       disabled={disableNext}
  //     >
  //       <ArrowDownIcon />
  //     </button>
  //   </div>
  // )
}

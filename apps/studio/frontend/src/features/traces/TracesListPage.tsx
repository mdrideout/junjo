import { Link, useParams } from 'react-router'
import TracesList from './TracesList'

export default function TracesListPage() {
  const { serviceName } = useParams()

  // Human readable start ingest time
  const date = new Date()
  const readableDate = date.toLocaleString()

  return (
    <div className={'px-2 py-3 flex flex-col h-dvh overflow-hidden'}>
      <div className={'px-2'}>
        <div className={'mb-1 flex gap-x-3 font-bold'}>
          <Link to={'/logs'} className={'hover:underline'}>
            Logs
          </Link>
          <div>&rarr;</div>
          <div>{serviceName}</div>
          <div>&rarr;</div>
          <div>Traces</div>
        </div>
        <div className={'text-zinc-400 text-xs'}>{readableDate}</div>
      </div>
      <hr className={'my-6'} />
      <div className={'grow overflow-scroll'}>
        <TracesList />
      </div>
    </div>
  )
}

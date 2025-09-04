import { Link, useParams } from 'react-router'
import TracesList from './TracesList'

export default function TracesListPage() {
  const { serviceName } = useParams()

  // Human readable start ingest time
  const date = new Date()
  const readableDate = date.toLocaleString()

  return (
    <div className={'p-5 pb-0 h-full flex flex-col '}>
      <div className={'px-2'}>
        <div className={'mb-1 flex gap-x-3 font-bold'}>
          <Link to={'/logs'} className={'hover:underline'}>
            Logs
          </Link>
          <div>&rarr;</div>
          <div>{serviceName}</div>
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

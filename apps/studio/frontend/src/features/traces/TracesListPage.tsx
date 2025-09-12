import { Link, useParams } from 'react-router'
import TracesList from './TracesList'
import { useState } from 'react'

export default function TracesListPage() {
  const { serviceName } = useParams()
  const [filterLLM, setFilterLLM] = useState(true)

  // Human readable start ingest time
  const date = new Date()
  const readableDate = date.toLocaleString()

  return (
    <div className={'px-2 py-3 flex flex-col h-dvh overflow-hidden'}>
      <div className={'px-2 pb-2'}>
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
        <div className="pt-2">
          <label className="inline-flex items-center">
            <input
              type="checkbox"
              className="form-checkbox"
              checked={filterLLM}
              onChange={(e) => setFilterLLM(e.target.checked)}
            />
            <span className="ml-2 text-sm">LLM Spans</span>
          </label>
        </div>
      </div>
      <hr />
      <div className={'grow overflow-scroll pt-2'}>
        <TracesList filterLLM={filterLLM} />
      </div>
    </div>
  )
}

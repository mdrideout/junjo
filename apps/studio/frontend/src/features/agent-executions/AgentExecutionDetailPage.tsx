import { useEffect } from 'react'
import { useParams } from 'react-router'
import ErrorPage from '../../components/errors/ErrorPage'
import { useAppDispatch, useAppSelector } from '../../root-store/hooks'
import { AgentExecutionDetailView } from './components/AgentExecutionDetailView'
import { SpanIdSchema, TraceIdSchema } from './schemas/agent-execution'
import { AgentExecutionsActions } from './store/slice'
import { selectAgentExecutionDetailRequest } from './store/selectors'

export default function AgentExecutionDetailPage() {
  const { traceId, agentSpanId } = useParams()
  const identityIsValid =
    TraceIdSchema.safeParse(traceId).success && SpanIdSchema.safeParse(agentSpanId).success
  const dispatch = useAppDispatch()
  const request = useAppSelector((state) =>
    selectAgentExecutionDetailRequest(state, {
      traceId: traceId ?? '',
      agentSpanId: agentSpanId ?? '',
    }),
  )

  useEffect(() => {
    if (identityIsValid && traceId && agentSpanId) {
      dispatch(AgentExecutionsActions.fetchAgentExecutionDetail({ traceId, agentSpanId }))
    }
  }, [agentSpanId, dispatch, identityIsValid, traceId])

  if (!identityIsValid) {
    return (
      <ErrorPage
        title="Invalid Agent execution"
        message="A 32-character lowercase hexadecimal trace ID and 16-character Agent span ID are required."
      />
    )
  }

  if (request.loading && request.data === null) {
    return <div className="p-6 text-sm text-[var(--studio-text-muted)]">Loading Agent execution…</div>
  }

  if (request.error !== null) {
    return <ErrorPage title="Agent execution unavailable" message={request.error} />
  }

  if (request.data === null) {
    return <div className="p-6 text-sm text-[var(--studio-text-muted)]">No Agent execution found.</div>
  }

  return <AgentExecutionDetailView detail={request.data} />
}

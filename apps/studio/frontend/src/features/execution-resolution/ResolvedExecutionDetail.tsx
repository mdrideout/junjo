import AgentExecutionDetailPage from '../agent-executions/AgentExecutionDetailPage'
import WorkflowDetailPage from '../junjo-data/workflow-detail/WorkflowDetailPage'
import {
  WorkflowDetailRouteProvider,
} from '../junjo-data/workflow-detail/workflow-detail-route'
import TraceDetails from '../traces/TraceDetails'
import type { ExecutionResolution, ExecutionResolutionRequest } from './schemas'

export function ResolvedExecutionDetail({
  request,
  resolution,
}: {
  request: ExecutionResolutionRequest
  resolution: ExecutionResolution
}) {
  if (request.destination === 'trace') {
    return (
      <TraceDetails
        routeIdentity={{
          serviceName: resolution.service_name,
          traceId: resolution.trace_id,
          spanId: resolution.span_id,
        }}
      />
    )
  }

  if (resolution.executable_type === 'agent') {
    return (
      <AgentExecutionDetailPage
        routeIdentity={{
          traceId: resolution.trace_id,
          agentSpanId: resolution.span_id,
        }}
      />
    )
  }

  return (
    <WorkflowDetailRouteProvider
      identity={{
        serviceName: resolution.service_name,
        traceId: resolution.trace_id,
        workflowSpanId: resolution.span_id,
      }}
    >
      <WorkflowDetailPage />
    </WorkflowDetailRouteProvider>
  )
}

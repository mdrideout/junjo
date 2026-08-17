import type { PublicConfig, Turn } from '../api/schemas'
import { studioResolutionUrl } from '../studio/links'

interface RunReferenceProps {
  label: string
  runtimeId: string | null
  studioUrl: string | null
}

function RunReference({ label, runtimeId, studioUrl }: RunReferenceProps) {
  if (runtimeId === null) return null
  return (
    <div>
      <dt>{label}</dt>
      <dd>
        {studioUrl === null ? (
          runtimeId
        ) : (
          <a href={studioUrl} target="_blank" rel="noreferrer">
            {runtimeId}
          </a>
        )}
      </dd>
    </div>
  )
}

interface TurnDiagnosticsProps {
  turn: Turn
  config: PublicConfig | null
}

export function TurnDiagnostics({ turn, config }: TurnDiagnosticsProps) {
  const { workflow_run_id: workflowRunId, agent_run_id: agentRunId } = (
    turn.execution_references
  )
  const workflowUrl = config === null || workflowRunId === null
    ? null
    : studioResolutionUrl(config, 'workflow', workflowRunId)
  const agentUrl = config === null || agentRunId === null
    ? null
    : studioResolutionUrl(config, 'agent', agentRunId)
  const traceUrl = config === null || workflowRunId === null
    ? null
    : studioResolutionUrl(config, 'workflow', workflowRunId, 'trace')
  const failure = turn.failure
  const failureUrl = config === null || workflowRunId === null || failure === null
    ? null
    : studioResolutionUrl(config, 'workflow', workflowRunId, 'failures')

  return (
    <details className="turn-diagnostics" open={failure !== null}>
      <summary>Turn diagnostics</summary>
      <dl aria-label="Turn diagnostics">
        <div>
          <dt>Turn</dt>
          <dd>{turn.id}</dd>
        </div>
        <div>
          <dt>Status</dt>
          <dd>{turn.status}</dd>
        </div>
        {failure !== null && (
          <>
            <div>
              <dt>Failure code</dt>
              <dd>{failure.code}</dd>
            </div>
            <div>
              <dt>Detail</dt>
              <dd>{failure.detail}</dd>
            </div>
            {failure.termination_reason !== null && (
              <div>
                <dt>Termination</dt>
                <dd>{failure.termination_reason}</dd>
              </div>
            )}
          </>
        )}
        <RunReference label="Workflow run" runtimeId={workflowRunId} studioUrl={workflowUrl} />
        <RunReference label="Agent run" runtimeId={agentRunId} studioUrl={agentUrl} />
        {failureUrl !== null && (
          <div>
            <dt>Failed node</dt>
            <dd><a href={failureUrl} target="_blank" rel="noreferrer">Open failures in Studio</a></dd>
          </div>
        )}
        {traceUrl !== null && (
          <div>
            <dt>Full trace</dt>
            <dd><a href={traceUrl} target="_blank" rel="noreferrer">Open in Studio</a></dd>
          </div>
        )}
      </dl>
    </details>
  )
}

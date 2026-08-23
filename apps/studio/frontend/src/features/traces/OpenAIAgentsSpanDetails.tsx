import SpanAttributeKeyValueViewer from '../../components/SpanAttributeKeyValueViewer'
import type { OpenAIAgentsTelemetry } from './schemas/openai-agents-telemetry'
import type { ReactNode } from 'react'

const SOURCE_TYPE_LABELS: Record<string, string> = {
  agent: 'Agent',
  custom: 'Custom span',
  function: 'Function tool',
  generation: 'Generation',
  guardrail: 'Guardrail',
  handoff: 'Handoff',
  mcp_tools: 'MCP tool listing',
  response: 'Response',
  speech: 'Speech',
  speech_group: 'Speech group',
  task: 'Task',
  transcription: 'Transcription',
  turn: 'Turn',
}

interface OpenAIAgentsSpanDetailsProps {
  telemetry: OpenAIAgentsTelemetry
}

export default function OpenAIAgentsSpanDetails({ telemetry }: OpenAIAgentsSpanDetailsProps) {
  if (telemetry.kind === 'invalid') {
    return (
      <DetailsSection>
        <div className="text-sm text-amber-700 dark:text-amber-400">
          Studio could not parse this OpenAI Agents SDK version 1 payload.
        </div>
        {telemetry.sourceType && <LabeledValue label="Source type" value={telemetry.sourceType} />}
        <LabeledValue label="Raw payload" value={telemetry.rawPayload} />
      </DetailsSection>
    )
  }

  if (telemetry.kind === 'trace') {
    return (
      <DetailsSection>
        <LabeledValue label="Source type" value="Workflow trace" />
        <LabeledValue label="Source trace ID" value={telemetry.payload.trace_id} />
        <LabeledValue label="Workflow data" value={telemetry.payload.metadata} />
        <LabeledValue label="Raw payload" value={telemetry.rawPayload} />
      </DetailsSection>
    )
  }

  const sourceLabel = SOURCE_TYPE_LABELS[telemetry.sourceType] ?? telemetry.sourceType
  return (
    <DetailsSection>
      <LabeledValue label="Source type" value={sourceLabel} />
      {!telemetry.knownSourceType && (
        <div className="text-sm text-amber-700 dark:text-amber-400">
          This source type is not recognized by this Studio version. Its complete payload is retained below.
        </div>
      )}
      <LabeledValue label="Source trace ID" value={telemetry.payload.trace_id} />
      <LabeledValue label="Source span ID" value={telemetry.payload.span_id} />
      <LabeledValue label="Source parent span ID" value={telemetry.payload.parent_span_id ?? 'None'} />
      <LabeledValue label={`${sourceLabel} data`} value={telemetry.payload.data} />
      {telemetry.payload.error !== null && <LabeledValue label="Source error" value={telemetry.payload.error} />}
      <LabeledValue label="Raw payload" value={telemetry.rawPayload} />
    </DetailsSection>
  )
}

function DetailsSection({ children }: { children: ReactNode }) {
  return (
    <section className="mb-6" aria-label="OpenAI Agents SDK telemetry">
      <div className="font-semibold text-md mb-2 text-lg">OpenAI Agents SDK</div>
      <div className="grid grid-cols-1 gap-2">{children}</div>
    </section>
  )
}

function LabeledValue({ label, value }: { label: string; value: unknown }) {
  return (
    <div className="border-b border-zinc-200 dark:border-zinc-700 pb-2">
      <div className="text-xs text-zinc-500">{label}</div>
      <div className="text-sm">
        <SpanAttributeKeyValueViewer value={value} />
      </div>
    </div>
  )
}

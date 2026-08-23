import type { RefObject } from 'react'
import SpanAttributeKeyValueViewer from '../../components/SpanAttributeKeyValueViewer'
import { OtelSpan } from './schemas/schemas'
import { wrapSpan } from './utils/span-accessor'
import OpenAIAgentsSpanDetails from './OpenAIAgentsSpanDetails'
import {
  OPENAI_AGENTS_SPAN_DATA_ATTRIBUTE,
  OPENAI_AGENTS_TRACE_DATA_ATTRIBUTE,
  parseOpenAIAgentsTelemetry,
} from './schemas/openai-agents-telemetry'

interface SpanAttributesContentProps {
  span: OtelSpan
  failureSectionRef?: RefObject<HTMLDivElement | null>
}

export default function SpanAttributesContent(props: SpanAttributesContentProps) {
  const { span, failureSectionRef } = props
  const firstFailureEventIndex = span.events_json.findIndex(
    (event) => event.name === 'exception' || event.name === 'junjo.hook_error',
  )
  const attributesAreFailureTarget =
    firstFailureEventIndex === -1 && Boolean(wrapSpan(span).errorType)
  const openAIAgentsTelemetry = parseOpenAIAgentsTelemetry(span.attributes_json)
  const visibleAttributes = Object.entries(span.attributes_json).filter(
    ([key]) =>
      openAIAgentsTelemetry === null ||
      (key !== OPENAI_AGENTS_SPAN_DATA_ATTRIBUTE && key !== OPENAI_AGENTS_TRACE_DATA_ATTRIBUTE),
  )

  return (
    <>
      <div className="mb-6">
        <div className="font-semibold text-md mb-2 text-lg">Basic Information</div>
        <div className="grid grid-cols-1 gap-2">
          <div>
            <div className="text-xs text-zinc-500">Name</div>
            <div className="font-mono text-sm">{span.name}</div>
          </div>
          <div>
            <div className="text-xs text-zinc-500">Span ID</div>
            <div className="font-mono text-sm">{span.span_id}</div>
          </div>
          <div>
            <div className="text-xs text-zinc-500">Parent Span ID</div>
            <div className="font-mono text-sm">{span.parent_span_id || 'None'}</div>
          </div>
          <div>
            <div className="text-xs text-zinc-500">Trace ID</div>
            <div className="font-mono text-sm">{span.trace_id}</div>
          </div>
          <div>
            <div className="text-xs text-zinc-500">Service Name</div>
            <div className="font-mono text-sm">{span.service_name}</div>
          </div>
          <div>
            <div className="text-xs text-zinc-500">Kind</div>
            <div className="font-mono text-sm">{span.kind}</div>
          </div>
          <div>
            <div className="text-xs text-zinc-500">Status</div>
            <div className="font-mono text-sm">{span.status_code}</div>
          </div>
        </div>
      </div>

      {openAIAgentsTelemetry && <OpenAIAgentsSpanDetails telemetry={openAIAgentsTelemetry} />}

      <div ref={attributesAreFailureTarget ? failureSectionRef : undefined} className="mb-6">
        <div className="font-semibold text-md mb-2 text-lg">Attributes</div>
        {visibleAttributes.length > 0 ? (
          <div className="grid grid-cols-1 gap-2">
            {visibleAttributes.map(([key, value]) => (
              <div key={key} className="border-b border-zinc-200 dark:border-zinc-700 pb-2">
                <div className="text-xs text-zinc-500">{key}</div>
                <div className="text-sm">
                  <SpanAttributeKeyValueViewer value={value} />
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="text-zinc-500 italic">No attributes</div>
        )}
      </div>

      <div className="mb-6">
        <div className="font-semibold text-md mb-2 text-lg">Events</div>
        {span.events_json.length > 0 ? (
          <div className="space-y-3">
            {span.events_json.map((event, index) => (
              <div
                key={index}
                ref={index === firstFailureEventIndex ? failureSectionRef : undefined}
                className="border border-zinc-200 dark:border-zinc-700 rounded p-2"
              >
                <div className="font-semibold">{event.name}</div>
                {event.attributes && Object.keys(event.attributes).length > 0 ? (
                  <div className="mt-2 grid grid-cols-1 gap-1">
                    {Object.entries(event.attributes).map(([key, value]) => (
                      <div key={key} className="text-xs mb-2">
                        <div className="text-zinc-500">{key}: </div>
                        <div className="text-sm">
                          <SpanAttributeKeyValueViewer value={value} />
                        </div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="text-zinc-500 italic text-xs">No event attributes</div>
                )}
              </div>
            ))}
          </div>
        ) : (
          <div className="text-zinc-500 italic">No events</div>
        )}
      </div>

      <div>
        <div className="font-semibold text-md mb-2 text-lg">Time</div>
        <div className="grid grid-cols-1 gap-2">
          <div>
            <div className="text-xs text-zinc-500">Start Time</div>
            <div className="font-mono text-sm">{span.start_time}</div>
          </div>
          <div>
            <div className="text-xs text-zinc-500">End Time</div>
            <div className="font-mono text-sm">{span.end_time}</div>
          </div>
        </div>
      </div>
    </>
  )
}

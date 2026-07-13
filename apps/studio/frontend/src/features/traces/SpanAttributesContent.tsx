import SpanAttributeKeyValueViewer from '../../components/SpanAttributeKeyValueViewer'
import { OtelSpan } from './schemas/schemas'
import { isLLMSpan } from './utils/span-utils'
import { Link } from 'react-router'

interface SpanAttributesContentProps {
  span: OtelSpan
  origin?: 'traces' | 'workflows'
  workflowSpanId?: string
}

export default function SpanAttributesContent(props: SpanAttributesContentProps) {
  const { span, origin = 'traces', workflowSpanId } = props

  // Generate playground link based on origin
  const getPlaygroundLink = () => {
    if (origin === 'workflows' && workflowSpanId) {
      return `/workflows/${span.service_name}/${span.trace_id}/${workflowSpanId}/${span.span_id}/prompt-playground`
    }
    return `/traces/${span.service_name}/${span.trace_id}/${span.span_id}/prompt-playground`
  }

  return (
    <>
      {isLLMSpan(span) && (
        <div className="mb-4">
          <Link
            to={getPlaygroundLink()}
            className="px-3 py-1.5 text-sm font-semibold rounded-md bg-zinc-900 dark:bg-zinc-700 text-white hover:bg-zinc-800"
          >
            Open in Playground
          </Link>
        </div>
      )}

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

      <div className="mb-6">
        <div className="font-semibold text-md mb-2 text-lg">Attributes</div>
        {Object.keys(span.attributes_json).length > 0 ? (
          <div className="grid grid-cols-1 gap-2">
            {Object.entries(span.attributes_json).map(([key, value]) => (
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
              <div key={index} className="border border-zinc-200 dark:border-zinc-700 rounded p-2">
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

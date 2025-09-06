import { OtelSpan } from '../otel/schemas/schemas'

interface SpanAttributesPanelProps {
  span: OtelSpan | null
}

export default function SpanAttributesPanel(props: SpanAttributesPanelProps) {
  const { span } = props

  if (!span) {
    return (
      <div className="p-4 h-full flex flex-col">
        <div className="text-lg font-semibold mb-4">Span Details</div>
        <div className="text-zinc-500 italic">No span selected</div>
      </div>
    )
  }

  return (
    <div className="p-4 h-full flex flex-col overflow-auto">
      <div className="text-xl font-semibold mb-4">Span Details</div>

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
                <div className="font-mono text-sm break-words">{JSON.stringify(value)}</div>
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
                        <div className="font-mono text-sm break-words">{JSON.stringify(value)}</div>
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
            <div className="font-mono text-sm text-sm">{span.start_time}</div>
          </div>
          <div>
            <div className="text-xs text-zinc-500">End Time</div>
            <div className="font-mono text-sm text-sm">{span.end_time}</div>
          </div>
        </div>
      </div>
    </div>
  )
}

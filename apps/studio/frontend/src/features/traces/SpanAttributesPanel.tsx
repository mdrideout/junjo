import { OtelSpan } from './schemas/schemas'
import SpanAttributesContent from './SpanAttributesContent'

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
      <SpanAttributesContent span={span} />
    </div>
  )
}

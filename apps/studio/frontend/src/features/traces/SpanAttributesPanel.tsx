import { useEffect, useRef } from 'react'
import { OtelSpan } from './schemas/schemas'
import SpanAttributesContent from './SpanAttributesContent'

interface SpanAttributesPanelProps {
  span: OtelSpan | null
  focusFailuresTrigger?: number | null
}

export default function SpanAttributesPanel(props: SpanAttributesPanelProps) {
  const { span, focusFailuresTrigger } = props
  const failureSectionRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (focusFailuresTrigger == null) return
    failureSectionRef.current?.scrollIntoView({ block: 'start' })
  }, [focusFailuresTrigger, span?.span_id])

  if (!span) {
    return (
      <div className="p-4 h-full flex flex-col">
        <div className="text-lg font-semibold mb-4">Span Details</div>
        <div className="text-zinc-500 italic">No span selected</div>
      </div>
    )
  }

  return (
    <div className="flex flex-col p-4">
      <div className="text-xl font-semibold mb-4">Span Details</div>
      <SpanAttributesContent
        span={span}
        failureSectionRef={failureSectionRef}
      />
    </div>
  )
}

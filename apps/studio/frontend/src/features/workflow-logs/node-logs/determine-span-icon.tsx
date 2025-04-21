import { JSX } from 'react'
import { JunjoSpanType, OtelSpan } from '../../otel/store/schemas'
import {
  CubeIcon,
  Square3Stack3DIcon,
  Squares2X2Icon,
  ChatBubbleLeftEllipsisIcon,
  CircleStackIcon,
} from '@heroicons/react/24/solid'

/**
 * Span Icon Constructor
 * Returns the icon for the span based on attribute information
 * @param span
 */
export function SpanIconConstructor(props: { span: OtelSpan; active: boolean }): JSX.Element {
  const { span, active } = props

  const attributes = span.attributes_json
  const iconColor = active ? 'text-amber-500' : 'text-zinc-600 dark:text-zinc-400'

  // Junjo Workflow Span
  if (span.junjo_span_type === JunjoSpanType.SUBFLOW) {
    return <Square3Stack3DIcon className={`size-5 ${iconColor}`} />
  }

  // Junjo Node Span
  if (span.junjo_span_type === JunjoSpanType.NODE) {
    return <CubeIcon className={`size-5 ${iconColor}`} />
  }

  // Junjo NodeGather Span
  if (span.junjo_span_type === JunjoSpanType.RUN_CONCURRENT) {
    return <Squares2X2Icon className={`size-5 ${iconColor}`} />
  }

  // Database Span
  // If attributes contains "db.system" key
  if (attributes['db.system']) {
    return <CircleStackIcon className={`size-5 ${iconColor}`} />
  }

  // AI Span
  // Gemini: gen_ai.system
  if (attributes['gen_ai.system']) {
    return <ChatBubbleLeftEllipsisIcon className={`size-5 ${iconColor}`} />
  }

  // Default
  return <div></div>
}

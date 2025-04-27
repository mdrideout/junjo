import { JSX } from 'react'
import { JunjoSpanType, OtelSpan } from '../../otel/store/schemas'
import {
  CubeIcon,
  Square3Stack3DIcon,
  Squares2X2Icon,
  ChatBubbleLeftEllipsisIcon,
  CircleStackIcon,
  QuestionMarkCircleIcon,
} from '@heroicons/react/24/solid'

/**
 * Span Icon Constructor
 * Returns the icon for the span based on attribute information
 * @param span
 */
export function SpanIconConstructor(props: {
  span: OtelSpan | undefined
  active: boolean
  size?: string
}): JSX.Element {
  const { span, active, size = 'size-5' } = props
  const iconColor = active ? 'text-amber-500' : 'text-zinc-600 dark:text-zinc-400'

  // Undefined
  if (span === undefined) {
    return <QuestionMarkCircleIcon className={`${size} ${iconColor}`} />
  }

  const attributes = span.attributes_json

  // Junjo Workflow Span
  if (span.junjo_span_type === JunjoSpanType.SUBFLOW) {
    return <Square3Stack3DIcon className={`${size} ${iconColor}`} />
  }

  // Junjo Node Span
  if (span.junjo_span_type === JunjoSpanType.NODE) {
    return <CubeIcon className={`${size} ${iconColor}`} />
  }

  // Junjo NodeGather Span
  if (span.junjo_span_type === JunjoSpanType.RUN_CONCURRENT) {
    return <Squares2X2Icon className={`${size} ${iconColor}`} />
  }

  // Database Span
  // If attributes contains "db.system" key
  if (attributes['db.system']) {
    return <CircleStackIcon className={`${size} ${iconColor}`} />
  }

  // AI Span
  // Gemini: gen_ai.system
  if (attributes['gen_ai.system']) {
    return <ChatBubbleLeftEllipsisIcon className={`${size} ${iconColor}`} />
  }

  // Default
  return <div></div>
}

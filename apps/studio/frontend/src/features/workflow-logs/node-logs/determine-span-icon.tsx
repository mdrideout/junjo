import { JSX } from 'react'
import { JunjoSpanType, OtelSpan } from '../../otel/store/schemas'
import { ChatBubbleLeftEllipsisIcon, CircleStackIcon } from '@heroicons/react/24/outline'
import { ArrowTurnDownRightIcon, CubeIcon, Square3Stack3DIcon } from '@heroicons/react/24/solid'

/**
 * Span Icon Constructor
 * Returns the icon for the span based on attribute information
 * @param span
 */
export function SpanIconConstructor(props: { span: OtelSpan }): JSX.Element {
  const { span } = props

  const attributes = span.attributes_json
  console.log(`Span ${span.name} attributes: `, attributes)
  console.log(`Span ${span.name} junjo type: `, span.junjo_span_type)

  // Junjo Workflow Span
  if (span.junjo_span_type === JunjoSpanType.WORKFLOW) {
    return <ArrowTurnDownRightIcon className={'size-5 text-zinc-600 dark:text-zinc-400'} />
  }

  // Junjo Node Span
  if (span.junjo_span_type === JunjoSpanType.NODE) {
    return <CubeIcon className={'size-5 text-zinc-600 dark:text-zinc-400'} />
  }

  // Junjo NodeGather Span
  if (span.junjo_span_type === JunjoSpanType.NODE_GATHER) {
    return <Square3Stack3DIcon className={'size-5 text-zinc-600 dark:text-zinc-400'} />
  }

  // Database Span
  // If attributes contains "db.system" key
  if (attributes['db.system']) {
    return <CircleStackIcon className={'size-5 text-zinc-600 dark:text-zinc-400'} />
  }

  // AI Span
  // Gemini: gen_ai.system
  if (attributes['gen_ai.system']) {
    return <ChatBubbleLeftEllipsisIcon className={'size-5 text-zinc-600 dark:text-zinc-400'} />
  }

  // Default
  return <div></div>
}

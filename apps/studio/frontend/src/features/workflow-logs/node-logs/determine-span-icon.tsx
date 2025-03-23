import { JSX } from 'react'
import { OtelSpan } from '../../otel/store/schemas'
import { ChatBubbleLeftEllipsisIcon, CircleStackIcon } from '@heroicons/react/24/outline'

/**
 * Span Icon Constructor
 * Returns the icon for the span based on attribute information
 * @param span
 */
export function SpanIconConstructor(props: { span: OtelSpan }): JSX.Element {
  const { span } = props

  const attributes = span.attributes_json
  console.log('Span attributes: ', attributes)

  // Database Span
  // If attributes contains "db.system" key
  if (attributes['db.system']) {
    return <CircleStackIcon className={'size-4 text-zinc-600'} />
  }

  // AI Span
  // Gemini: gen_ai.system
  if (attributes['gen_ai.system']) {
    return <ChatBubbleLeftEllipsisIcon className={'size-4 text-zinc-600'} />
  }

  // Default
  return <div></div>
}

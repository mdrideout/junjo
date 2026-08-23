import { JSX } from 'react'
import { OtelSpan } from '../../traces/schemas/schemas'
import {
  Squares2X2Icon,
  CircleStackIcon,
  QuestionMarkCircleIcon,
  SparklesIcon,
  CodeBracketIcon,
  ArrowsRightLeftIcon,
} from '@heroicons/react/24/solid'
import { OpenInferenceSpanKind } from '../../traces/schemas/attribute-schemas-openinference'
import { wrapSpan } from '../../traces/utils/span-accessor'
import { OpenAILogoIcon } from './openai-logo-icon'
import { JunjoLogoIcon } from './junjo-logo-icon'

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
  const accessor = wrapSpan(span)

  // Fixture-backed model spans performed no provider request. Keep the model
  // kind in the adjacent chip while using the code mark for its scripted source.
  if (attributes['junjo.model.fixture'] === true) {
    return <CodeBracketIcon data-span-icon="fixture" className={`${size} ${iconColor}`} />
  }

  // ============ JUNJO SPAN ICONS ============>
  // Native Junjo execution boundaries use the Junjo fish mark. Subflows are
  // presented as Workflows elsewhere in the trace tree.
  if (
    attributes['junjo.span_type'] === 'agent' ||
    accessor.isWorkflow ||
    accessor.isSubflow ||
    accessor.isNode
  ) {
    return <JunjoLogoIcon className={`${size} shrink-0 object-contain dark:invert`} />
  }

  // Junjo RunConcurrent Span
  if (accessor.isRunConcurrent) {
    return <Squares2X2Icon className={`${size} ${iconColor}`} />
  }

  // ============= DATABASE SPAN ICONS =============>
  // If attributes contains "db.system" key
  if (attributes['db.system']) {
    return <CircleStackIcon className={`${size} ${iconColor}`} />
  }

  // ============= OPENINFERENCE SPAN ICONS =============>
  // LLM spans (OpenInference or GenAI semantic conventions)
  //
  // OpenInference: openinference.span.kind === "LLM"
  // GenAI semconv (e.g. xAI): gen_ai.provider.name / gen_ai.operation.name present
  const openInferenceKind = attributes['openinference.span.kind']
  const genAiProvider = attributes['gen_ai.provider.name']
  const genAiOperation = attributes['gen_ai.operation.name']
  const openAIAgentsSchemaVersion = attributes['junjo.openai_agents.schema_version']
  const openAIAgentsSpanType = attributes['junjo.openai_agents.span.type']

  // OpenAI workflow, Agent, task, tool, turn, guardrail, and model boundaries receive the
  // OpenAI mark when Junjo's versioned source marker proves their identity.
  // Unrelated GenAI and native Junjo spans retain their normal icons.
  if (
    openAIAgentsSchemaVersion === 1 &&
    (genAiOperation === 'invoke_workflow' ||
      genAiOperation === 'invoke_agent' ||
      genAiOperation === 'execute_tool' ||
      openAIAgentsSpanType === 'task' ||
      openAIAgentsSpanType === 'turn' ||
      openAIAgentsSpanType === 'guardrail' ||
      openAIAgentsSpanType === 'generation' ||
      openAIAgentsSpanType === 'response')
  ) {
    return <OpenAILogoIcon className={`${size} scale-[1.2] ${iconColor}`} />
  }

  const isLLMSpan =
    attributes['junjo.agent.operation_type'] === 'model_request' ||
    openInferenceKind === OpenInferenceSpanKind.LLM ||
    (typeof genAiProvider === 'string' && genAiProvider.length > 0) ||
    (typeof genAiOperation === 'string' && genAiOperation.length > 0)

  if (isLLMSpan) {
    const providerRaw = attributes['llm.provider'] ?? genAiProvider
    const provider = typeof providerRaw === 'string' ? providerRaw.toLowerCase().trim() : ''

    // Provider-aware color (active selection only). Keep inactive spans muted.
    const providerColorMap: Record<string, string> = {
      'openai': 'text-emerald-500',
      'anthropic': 'text-orange-500',
      'google': 'text-blue-500',
      'gemini': 'text-blue-500',
      'xai': 'text-fuchsia-500',
    }

    const resolvedColor =
      active && provider && providerColorMap[provider]
        ? providerColorMap[provider]
        : iconColor

    return <SparklesIcon className={`${size} ${resolvedColor}`} />
  }

  // ============= OTEL STANDARD SPAN ICONS =============>
  if (span.kind === 'SERVER') {
    return <ArrowsRightLeftIcon className={`${size} ${iconColor}`} />
  }

  // ============= DEFAULT SPAN ICONS =============>
  // Default
  return <CodeBracketIcon data-span-icon="code" className={`${size} ${iconColor}`} />
}

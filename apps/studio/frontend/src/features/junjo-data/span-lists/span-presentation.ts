import {
  OpenInferenceLLMAttributesSchema,
  OpenInferenceSpanKind,
} from '../../traces/schemas/attribute-schemas-openinference'
import { OtelSpan } from '../../traces/schemas/schemas'

export type SpanKind = 'Agent' | 'LLM' | 'Node' | 'Tool' | 'Turn' | 'Workflow'

export interface SpanPresentation {
  kind: SpanKind | null
  name: string
}

/** Build the display kind and human name from truthful span attributes. */
export function spanPresentation(span: OtelSpan): SpanPresentation {
  const attributes = span.attributes_json

  const junjoSpanType = attributes['junjo.span_type']
  const junjoOperationType = attributes['junjo.agent.operation_type']
  if (junjoSpanType === 'agent') {
    return {
      kind: 'Agent',
      name: attributeName(attributes['junjo.agent.name'], span.name),
    }
  }
  if (junjoSpanType === 'node') {
    return { kind: 'Node', name: span.name }
  }
  if (junjoOperationType === 'model_request') {
    return {
      kind: 'LLM',
      name: attributeName(attributes['junjo.agent.model.name'], span.name, 'model request'),
    }
  }
  if (junjoOperationType === 'tool') {
    return {
      kind: 'Tool',
      name: attributeName(attributes['junjo.agent.tool.name'], span.name, 'tool'),
    }
  }
  if (junjoSpanType === 'workflow' || junjoSpanType === 'subflow') {
    return { kind: 'Workflow', name: span.name }
  }

  const openAIAgentsSpanType = attributes['junjo.openai_agents.span.type']
  if (openAIAgentsSpanType === 'turn') {
    return { kind: 'Turn', name: attributeName(undefined, span.name, 'turn') }
  }

  const genAiOperation = attributes['gen_ai.operation.name']
  if (typeof genAiOperation === 'string') {
    const agentName = attributes['gen_ai.agent.name']
    const workflowName = attributes['gen_ai.workflow.name']
    const toolName = attributes['gen_ai.tool.name']
    const modelName = attributes['gen_ai.response.model'] ?? attributes['gen_ai.request.model']
    if (genAiOperation === 'invoke_workflow') {
      return {
        kind: 'Workflow',
        name: attributeName(workflowName, span.name, genAiOperation),
      }
    }
    if (genAiOperation === 'invoke_agent') {
      return {
        kind: 'Agent',
        name: attributeName(agentName, span.name, genAiOperation),
      }
    }
    if (genAiOperation === 'execute_tool') {
      return {
        kind: 'Tool',
        name: attributeName(toolName, span.name, genAiOperation),
      }
    }
    if (['chat', 'text_completion', 'generate_content', 'responses'].includes(genAiOperation)) {
      return { kind: 'LLM', name: attributeName(modelName, span.name, genAiOperation) }
    }
  }

  // IF OpenInference LLM span
  if (attributes['openinference.span.kind'] === OpenInferenceSpanKind.LLM) {
    const parsedAttributes = OpenInferenceLLMAttributesSchema.safeParse(attributes)
    if (parsedAttributes.success) {
      return {
        kind: 'LLM',
        name: `${parsedAttributes.data['llm.provider']} — ${parsedAttributes.data['llm.model_name']}`,
      }
    }
  }

  return { kind: null, name: span.name }
}

function attributeName(candidate: unknown, fallback: string, fallbackPrefix?: string): string {
  if (typeof candidate === 'string' && candidate.length > 0) return candidate
  if (fallbackPrefix === undefined) return fallback

  const prefix = `${fallbackPrefix} `
  return fallback.startsWith(prefix) ? fallback.slice(prefix.length) : fallback
}

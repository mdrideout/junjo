import {
  OpenInferenceLLMAttributesSchema,
  OpenInferenceSpanKind,
} from '../../traces/schemas/attribute-schemas-openinference'
import { OtelSpan } from '../../traces/schemas/schemas'

export type SpanKind = 'Agent' | 'LLM' | 'Node' | 'Task' | 'Tool' | 'Turn' | 'Workflow'

export interface SpanPresentation {
  kind: SpanKind | null
  name: string
  fixture?: true
}

/** Build the display kind and human name from truthful span attributes. */
export function spanPresentation(span: OtelSpan): SpanPresentation {
  const attributes = span.attributes_json
  const present = (kind: SpanKind | null, name: string): SpanPresentation => {
    const presentation: SpanPresentation = { kind, name }
    return attributes['junjo.model.fixture'] === true
      ? { ...presentation, fixture: true }
      : presentation
  }

  const junjoSpanType = attributes['junjo.span_type']
  const junjoOperationType = attributes['junjo.agent.operation_type']
  if (junjoSpanType === 'agent') {
    return present('Agent', attributeName(attributes['junjo.agent.name'], span.name))
  }
  if (junjoSpanType === 'node') {
    return present('Node', span.name)
  }
  if (junjoOperationType === 'model_request') {
    return present(
      'LLM',
      attributeName(attributes['junjo.agent.model.name'], span.name, 'model request'),
    )
  }
  if (junjoOperationType === 'tool') {
    return present('Tool', attributeName(attributes['junjo.agent.tool.name'], span.name, 'tool'))
  }
  if (junjoSpanType === 'workflow' || junjoSpanType === 'subflow') {
    return present('Workflow', span.name)
  }

  const openAIAgentsSpanType = attributes['junjo.openai_agents.span.type']
  if (openAIAgentsSpanType === 'turn') {
    return present('Turn', attributeName(undefined, span.name, 'turn'))
  }
  if (openAIAgentsSpanType === 'task') {
    return present('Task', attributeName(undefined, span.name, 'task'))
  }

  const genAiOperation = attributes['gen_ai.operation.name']
  if (typeof genAiOperation === 'string') {
    const agentName = attributes['gen_ai.agent.name']
    const workflowName = attributes['gen_ai.workflow.name']
    const toolName = attributes['gen_ai.tool.name']
    const modelName = attributes['gen_ai.response.model'] ?? attributes['gen_ai.request.model']
    if (genAiOperation === 'invoke_workflow') {
      return present('Workflow', attributeName(workflowName, span.name, genAiOperation))
    }
    if (genAiOperation === 'invoke_agent') {
      return present('Agent', attributeName(agentName, span.name, genAiOperation))
    }
    if (genAiOperation === 'execute_tool') {
      return present('Tool', attributeName(toolName, span.name, genAiOperation))
    }
    if (['chat', 'text_completion', 'generate_content', 'responses'].includes(genAiOperation)) {
      return present('LLM', attributeName(modelName, span.name, genAiOperation))
    }
  }

  // IF OpenInference LLM span
  if (attributes['openinference.span.kind'] === OpenInferenceSpanKind.LLM) {
    const parsedAttributes = OpenInferenceLLMAttributesSchema.safeParse(attributes)
    if (parsedAttributes.success) {
      return present(
        'LLM',
        `${parsedAttributes.data['llm.provider']} — ${parsedAttributes.data['llm.model_name']}`,
      )
    }
  }

  return present(null, span.name)
}

function attributeName(candidate: unknown, fallback: string, fallbackPrefix?: string): string {
  if (typeof candidate === 'string' && candidate.length > 0) return candidate
  if (fallbackPrefix === undefined) return fallback

  const prefix = `${fallbackPrefix} `
  return fallback.startsWith(prefix) ? fallback.slice(prefix.length) : fallback
}

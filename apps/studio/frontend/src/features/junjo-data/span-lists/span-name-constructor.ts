import {
  OpenInferenceLLMAttributesSchema,
  OpenInferenceSpanKind,
} from '../../traces/schemas/attribute-schemas-openinference'
import { OtelSpan } from '../../traces/schemas/schemas'

/**
 * Span Name Constructor
 * Conditionally returns a span name based on various attributes.
 * Defaults to span.name if no matching attributes are found.
 */
export function spanNameConstructor(span: OtelSpan): string {
  const attributes = span.attributes_json

  const genAiOperation = attributes['gen_ai.operation.name']
  if (typeof genAiOperation === 'string') {
    const agentName = attributes['gen_ai.agent.name']
    const workflowName = attributes['gen_ai.workflow.name']
    const toolName = attributes['gen_ai.tool.name']
    const modelName = attributes['gen_ai.response.model'] ?? attributes['gen_ai.request.model']
    if (genAiOperation === 'invoke_workflow') {
      return label('Agent run', workflowName, span.name)
    }
    if (genAiOperation === 'invoke_agent') {
      return label('Agent', agentName, span.name)
    }
    if (genAiOperation === 'execute_tool') {
      return label('Tool call', toolName, span.name)
    }
    if (['chat', 'text_completion', 'generate_content', 'responses'].includes(genAiOperation)) {
      return label('Model call', modelName, span.name)
    }
  }

  // IF OpenInference LLM span
  if (attributes['openinference.span.kind'] === OpenInferenceSpanKind.LLM) {
    const parsedAttributes = OpenInferenceLLMAttributesSchema.safeParse(attributes)
    if (parsedAttributes.success) {
      return `${parsedAttributes.data['openinference.span.kind']} - ${parsedAttributes.data['llm.provider']} - ${parsedAttributes.data['llm.model_name']}`
    }
  }

  return span.name
}

function label(kind: string, candidate: unknown, fallback: string): string {
  return typeof candidate === 'string' && candidate.length > 0
    ? `${kind} — ${candidate}`
    : `${kind} — ${fallback}`
}

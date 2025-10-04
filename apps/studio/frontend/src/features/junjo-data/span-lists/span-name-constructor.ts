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

  // IF OpenInference LLM span
  if (attributes['openinference.span.kind'] === OpenInferenceSpanKind.LLM) {
    const parsedAttributes = OpenInferenceLLMAttributesSchema.safeParse(attributes)
    if (parsedAttributes.success) {
      return `${parsedAttributes.data['openinference.span.kind']} - ${parsedAttributes.data['llm.provider']} - ${parsedAttributes.data['llm.model_name']}`
    }
  }

  return span.name
}

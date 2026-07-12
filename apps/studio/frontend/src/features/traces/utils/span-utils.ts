import { OtelSpan } from '../schemas/schemas'
import { OpenInferenceSpanKind } from '../schemas/attribute-schemas-openinference'

export const isLLMSpan = (span: OtelSpan): boolean => {
  return span.attributes_json['openinference.span.kind'] === OpenInferenceSpanKind.LLM
}

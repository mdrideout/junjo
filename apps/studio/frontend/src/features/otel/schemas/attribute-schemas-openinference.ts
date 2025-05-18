// OpenInference attributes schemas
// https://github.com/Arize-ai/openinference/blob/main/spec/semantic_conventions.md#semantic-conventions

import { z } from 'zod'

export enum OpenInferenceSpanKind {
  LLM = 'LLM',
  CHAIN = 'CHAIN',
  RETRIEVER = 'RETRIEVER',
  RERANKER = 'RERANKER',
}

export const OpenInferenceLLMAttributesSchema = z.object({
  'openinference.span.kind': z.union([z.nativeEnum(OpenInferenceSpanKind), z.string()]),
  'llm.provider': z.string().optional(),
  'llm.model_name': z.string().optional(),
  'output.mime_type': z.string().optional(),
  'input.mime_type': z.string().optional(),
  'input.value': z.string().optional(),
  'output.value': z.string().optional(),
})
export type OpenInferenceLLMAttributes = z.infer<typeof OpenInferenceLLMAttributesSchema>

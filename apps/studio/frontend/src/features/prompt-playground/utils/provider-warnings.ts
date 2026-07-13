import { OtelSpan } from '../../traces/schemas/schemas'
import type { JsonSchema } from './schema-utils'

// Structure for provider-specific warnings
export interface ProviderWarning {
  title: string
  description: string
  codeExampleBad: string
  codeExampleGood: string
  learnMoreUrl?: string
}

// Structure for JSON schema info (informational, not a warning)
export interface JsonSchemaInfo {
  schema: JsonSchema
}

// Detection function signature
type WarningDetector = (span: OtelSpan) => ProviderWarning | null

function isJsonObject(value: unknown): value is JsonSchema {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function parseJsonObject(value: string): JsonSchema | null {
  try {
    const parsed: unknown = JSON.parse(value)
    return isJsonObject(parsed) ? parsed : null
  } catch {
    return null
  }
}

function getInvocationParameters(value: unknown): JsonSchema | null {
  if (typeof value === 'string') {
    return parseJsonObject(value)
  }
  return isJsonObject(value) ? value : null
}

// Gemini-specific detector for response_schema vs response_json_schema
function detectGeminiWarnings(span: OtelSpan): ProviderWarning | null {
  const provider = span.attributes_json['llm.provider']

  // Only run for Gemini/Google
  if (provider !== 'google' && provider !== 'gemini') {
    return null
  }

  // Check both input.value and llm.invocation_parameters
  let hasResponseSchema = false

  // Check input.value (string representation of config)
  const inputValue = span.attributes_json['input.value']
  if (typeof inputValue === 'string') {
    if (inputValue.includes('response_schema=') && !inputValue.includes('response_schema=None')) {
      hasResponseSchema = true
    }
  }

  // Check llm.invocation_parameters (can be string or already-parsed object)
  const invocationParams = span.attributes_json['llm.invocation_parameters']

  if (typeof invocationParams === 'string') {
    const parsed = parseJsonObject(invocationParams)
    if (parsed) {
      if (parsed.response_schema !== null && parsed.response_schema !== undefined) {
        hasResponseSchema = true
      }
    } else {
      // If parsing fails, check string pattern
      if (
        invocationParams.includes('response_schema=') &&
        !invocationParams.includes('response_schema=None')
      ) {
        hasResponseSchema = true
      }
    }
  } else if (isJsonObject(invocationParams)) {
    if (invocationParams.response_schema !== null && invocationParams.response_schema !== undefined) {
      hasResponseSchema = true
    }
  }

  if (hasResponseSchema) {
    return {
      title: 'Improve Telemetry: Use response_json_schema',
      description:
        'Using the response_schema parameter with a Pydantic class only captures the class name in telemetry. The genai library internally calls the .model_json_schema() on the Pydantic model before sending the request. If you explicitly call .model_json_schema() first, and pass that as the response_json_schema attribute, it produces an identical LLM call. However, using response_json_schema explicitly captures the full schema structure in telemetry, enabling better observability and allowing schema reconstruction in prompt playgrounds.',
      codeExampleBad: `# ❌ Bad: Only captures class name in telemetry
from google import genai
from pydantic import BaseModel

class OutputSchema(BaseModel):
    result: str
    items: list[str]

client = genai.Client(api_key="...")
response = client.models.generate_content(
    model="gemini-2.5-flash-lite-preview-06-17",
    contents="Your prompt here",
    config={
        "response_mime_type": "application/json",
        "response_schema": OutputSchema  # Only logs class name
        # ⚠️ Telemetry captures: "response_schema": "OutputSchema"
        # ⚠️ Library internally calls OutputSchema.model_json_schema()
        #    but that happens AFTER telemetry capture
    }
)`,
      codeExampleGood: `# ✅ Good: Captures full schema structure in telemetry
from google import genai
from pydantic import BaseModel

class OutputSchema(BaseModel):
    result: str
    items: list[str]

client = genai.Client(api_key="...")
response = client.models.generate_content(
    model="gemini-2.5-flash-lite-preview-06-17",
    contents="Your prompt here",
    config={
        "response_mime_type": "application/json",
        "response_json_schema": OutputSchema.model_json_schema()
        # ✅ Telemetry captures: full JSON schema with properties, types, etc.
        # ✅ Enables schema reconstruction in the playground
        # ✅ Same API request, better observability
    }
)`,
      learnMoreUrl: 'https://ai.google.dev/gemini-api/docs/structured-output#schemas-in-python',
    }
  }

  return null
}

// OpenAI-specific detector for JSON schema in response_format
export function detectOpenAIJsonSchema(span: OtelSpan): JsonSchemaInfo | null {
  const provider = span.attributes_json['llm.provider']

  // Only run for OpenAI
  if (provider !== 'openai') {
    return null
  }

  // Check llm.invocation_parameters for response_format.json_schema
  const invocationParams = span.attributes_json['llm.invocation_parameters']

  const parsed = getInvocationParameters(invocationParams)
  if (!parsed || !isJsonObject(parsed.response_format)) {
    return null
  }

  const responseFormat = parsed.response_format
  if (!isJsonObject(responseFormat.json_schema)) {
    return null
  }

  const jsonSchema = responseFormat.json_schema.schema
  if (isJsonObject(jsonSchema)) {
    return { schema: jsonSchema }
  }

  return null
}

// Anthropic-specific detector for JSON schema in tool definitions
export function detectAnthropicJsonSchema(span: OtelSpan): JsonSchemaInfo | null {
  const provider = span.attributes_json['llm.provider']

  // Only run for Anthropic
  if (provider !== 'anthropic') {
    return null
  }

  // Check llm.invocation_parameters for tools[].input_schema
  const invocationParams = span.attributes_json['llm.invocation_parameters']

  const parsed = getInvocationParameters(invocationParams)
  if (!parsed || !Array.isArray(parsed.tools)) {
    return null
  }

  const firstTool = parsed.tools[0]
  if (isJsonObject(firstTool) && isJsonObject(firstTool.input_schema)) {
    return { schema: firstTool.input_schema }
  }

  return null
}

// Gemini-specific detector for response_json_schema
export function detectGeminiJsonSchema(span: OtelSpan): JsonSchemaInfo | null {
  const provider = span.attributes_json['llm.provider']

  // Only run for Gemini/Google
  if (provider !== 'google' && provider !== 'gemini') {
    return null
  }

  // Check llm.invocation_parameters for response_json_schema
  const invocationParams = span.attributes_json['llm.invocation_parameters']

  const parsed = getInvocationParameters(invocationParams)
  if (parsed && isJsonObject(parsed.response_json_schema)) {
    return { schema: parsed.response_json_schema }
  }

  return null
}

// Unified JSON schema detector - tries all providers
export function detectJsonSchema(span: OtelSpan): JsonSchema | null {
  // Try provider-specific detectors
  const openaiResult = detectOpenAIJsonSchema(span)
  if (openaiResult) return openaiResult.schema

  const anthropicResult = detectAnthropicJsonSchema(span)
  if (anthropicResult) return anthropicResult.schema

  const geminiResult = detectGeminiJsonSchema(span)
  if (geminiResult) return geminiResult.schema

  return null
}

// Registry of provider detectors (extensible for future providers)
const PROVIDER_DETECTORS: WarningDetector[] = [
  detectGeminiWarnings,
  // Future: detectOpenAIWarnings, detectAnthropicWarnings, etc.
]

// Main detection function
export function detectProviderWarnings(span: OtelSpan): ProviderWarning | null {
  for (const detector of PROVIDER_DETECTORS) {
    const warning = detector(span)
    if (warning) return warning
  }
  return null
}

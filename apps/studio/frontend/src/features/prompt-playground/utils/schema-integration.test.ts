import { describe, it, expect } from 'vitest'
import { detectJsonSchema } from './provider-warnings'
import type { OtelSpan } from '../../traces/schemas/schemas'
import { JunjoSpanType } from '../../traces/schemas/schemas'

// Helper to create a minimal valid OtelSpan with defaults
const createBaseSpan = (): OtelSpan => ({
  span_id: 'test-span-id',
  trace_id: 'test-trace-id',
  service_name: 'test-service',
  attributes_json: {},
  start_time: '2025-01-01T00:00:00Z',
  end_time: '2025-01-01T00:00:01Z',
  events_json: [],
  kind: 'INTERNAL',
  links_json: [],
  name: 'test-span',
  parent_span_id: null,
  status_code: 'OK',
  status_message: '',
  trace_flags: 0,
  trace_state: null,
  junjo_id: '',
  junjo_parent_id: '',
  junjo_span_type: JunjoSpanType.OTHER,
  junjo_wf_state_start: {},
  junjo_wf_state_end: {},
  junjo_wf_graph_structure: {},
  junjo_wf_store_id: '',
})

// Mock OpenAI span with JSON schema
const createOpenAISpanWithSchema = (): OtelSpan => {
  const schema = {
    type: 'object',
    properties: {
      name: { type: 'string', description: 'The name of the person' },
      age: { type: 'number', description: 'The age of the person' },
      email: { type: 'string', format: 'email' },
    },
    required: ['name', 'age'],
    additionalProperties: false,
  }

  return {
    ...createBaseSpan(),
    trace_id: 'test-trace-openai',
    span_id: 'test-span-openai',
    name: 'openai-llm-call',
    attributes_json: {
      'llm.provider': 'openai',
      'llm.model_name': 'gpt-4',
      'input.mime_type': 'application/json',
      'llm.invocation_parameters': JSON.stringify({
        temperature: 0.7,
        max_tokens: 2048,
        response_format: {
          type: 'json_schema',
          json_schema: {
            name: 'person_schema',
            strict: true,
            schema: schema,
          },
        },
      }),
    },
  }
}

// Mock Anthropic span with JSON schema (tool-based)
const createAnthropicSpanWithSchema = (): OtelSpan => {
  const schema = {
    type: 'object',
    properties: {
      summary: { type: 'string', description: 'A summary of the content' },
      topics: { type: 'array', items: { type: 'string' }, description: 'List of topics' },
      sentiment: { type: 'string', enum: ['positive', 'negative', 'neutral'] },
    },
    required: ['summary', 'topics'],
  }

  return {
    ...createBaseSpan(),
    trace_id: 'test-trace-anthropic',
    span_id: 'test-span-anthropic',
    name: 'anthropic-llm-call',
    attributes_json: {
      'llm.provider': 'anthropic',
      'llm.model_name': 'claude-3-5-sonnet-20241022',
      'input.mime_type': 'application/json',
      'llm.invocation_parameters': JSON.stringify({
        temperature: 0.5,
        max_tokens: 4096,
        tools: [
          {
            name: 'structured_output',
            description: 'Return data in structured JSON format',
            input_schema: schema,
          },
        ],
        tool_choice: { type: 'tool', name: 'structured_output' },
      }),
    },
  }
}

// Mock Gemini span with JSON schema
const createGeminiSpanWithSchema = (): OtelSpan => {
  const schema = {
    type: 'object',
    properties: {
      title: { type: 'string', description: 'The title of the article' },
      content: { type: 'string', description: 'The main content' },
      tags: { type: 'array', items: { type: 'string' } },
      published: { type: 'boolean' },
    },
    required: ['title', 'content'],
  }

  return {
    ...createBaseSpan(),
    trace_id: 'test-trace-gemini',
    span_id: 'test-span-gemini',
    name: 'gemini-llm-call',
    attributes_json: {
      'llm.provider': 'google',
      'llm.model_name': 'gemini-2.5-flash',
      'input.mime_type': 'application/json',
      'llm.invocation_parameters': JSON.stringify({
        temperature: 0.8,
        maxOutputTokens: 2048,
        response_json_schema: schema,
      }),
    },
  }
}

// Mock span without JSON schema
const createSpanWithoutSchema = (provider: string): OtelSpan => {
  return {
    ...createBaseSpan(),
    trace_id: 'test-trace-no-schema',
    span_id: 'test-span-no-schema',
    name: `${provider}-llm-call-no-schema`,
    attributes_json: {
      'llm.provider': provider,
      'llm.model_name': 'test-model',
      'llm.invocation_parameters': JSON.stringify({
        temperature: 0.7,
        max_tokens: 2048,
      }),
    },
  }
}

describe('Schema Detection for UI Display', () => {
  it('should detect OpenAI schema for UI display', () => {
    const span = createOpenAISpanWithSchema()
    const jsonSchema = detectJsonSchema(span)
    const jsonSchemaInfo = jsonSchema ? { schema: jsonSchema } : null

    expect(jsonSchemaInfo).not.toBeNull()
    expect(jsonSchemaInfo?.schema).toHaveProperty('type', 'object')
    expect(jsonSchemaInfo?.schema).toHaveProperty('properties')
    expect(jsonSchemaInfo?.schema.properties).toHaveProperty('name')
    expect(jsonSchemaInfo?.schema.properties).toHaveProperty('age')
  })

  it('should detect Anthropic schema for UI display', () => {
    const span = createAnthropicSpanWithSchema()
    const jsonSchema = detectJsonSchema(span)
    const jsonSchemaInfo = jsonSchema ? { schema: jsonSchema } : null

    expect(jsonSchemaInfo).not.toBeNull()
    expect(jsonSchemaInfo?.schema).toHaveProperty('type', 'object')
    expect(jsonSchemaInfo?.schema).toHaveProperty('properties')
    expect(jsonSchemaInfo?.schema.properties).toHaveProperty('summary')
    expect(jsonSchemaInfo?.schema.properties).toHaveProperty('topics')
  })

  it('should detect Gemini schema for UI display', () => {
    const span = createGeminiSpanWithSchema()
    const jsonSchema = detectJsonSchema(span)
    const jsonSchemaInfo = jsonSchema ? { schema: jsonSchema } : null

    expect(jsonSchemaInfo).not.toBeNull()
    expect(jsonSchemaInfo?.schema).toHaveProperty('type', 'object')
    expect(jsonSchemaInfo?.schema).toHaveProperty('properties')
    expect(jsonSchemaInfo?.schema.properties).toHaveProperty('title')
  })

  it('should return null when no schema present', () => {
    const span = createSpanWithoutSchema('openai')
    const jsonSchema = detectJsonSchema(span)
    const jsonSchemaInfo = jsonSchema ? { schema: jsonSchema } : null

    expect(jsonSchemaInfo).toBeNull()
  })
})

describe('Structured Output Toggle Logic', () => {
  describe('Scenario 1: Toggle ON + Schema Detected', () => {
    it('OpenAI: should detect schema for structured output', () => {
      const span = createOpenAISpanWithSchema()
      const jsonMode = true
      const jsonSchema = detectJsonSchema(span)

      // Verify schema is detected
      expect(jsonSchema).not.toBeNull()
      expect(jsonSchema).toHaveProperty('type', 'object')

      // With jsonMode ON and schema present, should use structured output
      if (jsonMode && jsonSchema) {
        expect(jsonSchema).toHaveProperty('properties')
        expect(jsonSchema.properties).toHaveProperty('name')
      }
    })

    it('Anthropic: should detect schema for tool-based structured output', () => {
      const span = createAnthropicSpanWithSchema()
      const jsonMode = true
      const jsonSchema = detectJsonSchema(span)

      expect(jsonSchema).not.toBeNull()
      expect(jsonSchema).toHaveProperty('type', 'object')

      // With jsonMode ON and schema present, should use tools with input_schema
      if (jsonMode && jsonSchema) {
        expect(jsonSchema.properties).toHaveProperty('summary')
        expect(jsonSchema.properties).toHaveProperty('topics')
      }
    })

    it('Gemini: should detect schema for response_json_schema', () => {
      const span = createGeminiSpanWithSchema()
      const jsonMode = true
      const jsonSchema = detectJsonSchema(span)

      expect(jsonSchema).not.toBeNull()
      expect(jsonSchema).toHaveProperty('type', 'object')

      // With jsonMode ON and schema present, should use response_json_schema
      if (jsonMode && jsonSchema) {
        expect(jsonSchema.properties).toHaveProperty('title')
        expect(jsonSchema.properties).toHaveProperty('content')
      }
    })
  })

  describe('Scenario 2: Toggle ON + No Schema', () => {
    it('OpenAI: should return null (use schema-less JSON mode)', () => {
      const span = createSpanWithoutSchema('openai')
      const jsonMode = true
      const jsonSchema = detectJsonSchema(span)

      expect(jsonSchema).toBeNull()

      // With jsonMode ON but no schema, should use json_object type
      const shouldUseSchemalessMode = jsonMode && !jsonSchema
      expect(shouldUseSchemalessMode).toBe(true)
    })

    it('Anthropic: should return null (use schema-less JSON mode)', () => {
      const span = createSpanWithoutSchema('anthropic')
      const jsonMode = true
      const jsonSchema = detectJsonSchema(span)

      expect(jsonSchema).toBeNull()

      // With jsonMode ON but no schema, should use generic tool
      const shouldUseSchemalessMode = jsonMode && !jsonSchema
      expect(shouldUseSchemalessMode).toBe(true)
    })

    it('Gemini: should return null (use schema-less JSON mode)', () => {
      const span = createSpanWithoutSchema('google')
      const jsonMode = true
      const jsonSchema = detectJsonSchema(span)

      expect(jsonSchema).toBeNull()

      // With jsonMode ON but no schema, should use responseMimeType only
      const shouldUseSchemalessMode = jsonMode && !jsonSchema
      expect(shouldUseSchemalessMode).toBe(true)
    })
  })

  describe('Scenario 3: Toggle OFF + Schema Detected', () => {
    it('should NOT use schema when toggle is disabled (OpenAI)', () => {
      const span = createOpenAISpanWithSchema()
      const jsonMode = false
      const jsonSchema = detectJsonSchema(span)

      // Schema exists
      expect(jsonSchema).not.toBeNull()

      // But with jsonMode OFF, should NOT include schema in request
      const shouldIncludeSchema = jsonMode && jsonSchema
      expect(shouldIncludeSchema).toBe(false)
    })

    it('should NOT use schema when toggle is disabled (Anthropic)', () => {
      const span = createAnthropicSpanWithSchema()
      const jsonMode = false
      const jsonSchema = detectJsonSchema(span)

      expect(jsonSchema).not.toBeNull()

      const shouldIncludeSchema = jsonMode && jsonSchema
      expect(shouldIncludeSchema).toBe(false)
    })

    it('should NOT use schema when toggle is disabled (Gemini)', () => {
      const span = createGeminiSpanWithSchema()
      const jsonMode = false
      const jsonSchema = detectJsonSchema(span)

      expect(jsonSchema).not.toBeNull()

      const shouldIncludeSchema = jsonMode && jsonSchema
      expect(shouldIncludeSchema).toBe(false)
    })
  })

  describe('Scenario 4: Toggle OFF + No Schema', () => {
    it('should use normal text mode (OpenAI)', () => {
      const span = createSpanWithoutSchema('openai')
      const jsonMode = false
      const jsonSchema = detectJsonSchema(span)

      expect(jsonSchema).toBeNull()

      // Normal text mode - no JSON-related parameters
      const shouldUseStructuredOutput = jsonMode && jsonSchema
      const shouldUseSchemalessMode = jsonMode && !jsonSchema
      expect(shouldUseStructuredOutput).toBe(false)
      expect(shouldUseSchemalessMode).toBe(false)
    })

    it('should use normal text mode (Anthropic)', () => {
      const span = createSpanWithoutSchema('anthropic')
      const jsonMode = false
      const jsonSchema = detectJsonSchema(span)

      expect(jsonSchema).toBeNull()

      const shouldUseStructuredOutput = jsonMode && jsonSchema
      const shouldUseSchemalessMode = jsonMode && !jsonSchema
      expect(shouldUseStructuredOutput).toBe(false)
      expect(shouldUseSchemalessMode).toBe(false)
    })

    it('should use normal text mode (Gemini)', () => {
      const span = createSpanWithoutSchema('google')
      const jsonMode = false
      const jsonSchema = detectJsonSchema(span)

      expect(jsonSchema).toBeNull()

      const shouldUseStructuredOutput = jsonMode && jsonSchema
      const shouldUseSchemalessMode = jsonMode && !jsonSchema
      expect(shouldUseStructuredOutput).toBe(false)
      expect(shouldUseSchemalessMode).toBe(false)
    })
  })
})

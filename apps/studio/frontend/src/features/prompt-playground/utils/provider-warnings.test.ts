import { describe, it, expect } from 'vitest'
import {
  detectOpenAIJsonSchema,
  detectAnthropicJsonSchema,
  detectGeminiJsonSchema,
  detectJsonSchema,
} from './provider-warnings'
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

// Mock OpenInference span with OpenAI JSON schema
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

// Mock OpenInference span with Anthropic JSON schema (tool-based)
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

// Mock OpenInference span with Gemini JSON schema
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

// Mock span without JSON schema (basic JSON mode)
const createSpanWithoutSchema = (provider: string): OtelSpan => {
  return {
    ...createBaseSpan(),
    trace_id: 'test-trace-no-schema',
    span_id: 'test-span-no-schema',
    name: `${provider}-llm-call-no-schema`,
    attributes_json: {
      'llm.provider': provider,
      'llm.model_name': 'test-model',
      'input.mime_type': 'application/json',
      'llm.invocation_parameters': JSON.stringify({
        temperature: 0.7,
        max_tokens: 2048,
        ...(provider === 'openai' && { response_format: { type: 'json_object' } }),
      }),
    },
  }
}

describe('JSON Schema Detection', () => {
  describe('detectOpenAIJsonSchema', () => {
    it('should detect JSON schema from OpenAI span with structured output', () => {
      const span = createOpenAISpanWithSchema()
      const result = detectOpenAIJsonSchema(span)

      expect(result).not.toBeNull()
      expect(result?.schema).toHaveProperty('type', 'object')
      expect(result?.schema).toHaveProperty('properties')
      expect(result?.schema.properties).toHaveProperty('name')
      expect(result?.schema.properties).toHaveProperty('age')
      expect(result?.schema.required).toContain('name')
      expect(result?.schema.required).toContain('age')
    })

    it('should return null for OpenAI span without JSON schema', () => {
      const span = createSpanWithoutSchema('openai')
      const result = detectOpenAIJsonSchema(span)

      expect(result).toBeNull()
    })

    it('should return null for non-OpenAI span', () => {
      const span = createGeminiSpanWithSchema()
      const result = detectOpenAIJsonSchema(span)

      expect(result).toBeNull()
    })
  })

  describe('detectAnthropicJsonSchema', () => {
    it('should detect JSON schema from Anthropic span with tool-based JSON', () => {
      const span = createAnthropicSpanWithSchema()
      const result = detectAnthropicJsonSchema(span)

      expect(result).not.toBeNull()
      expect(result?.schema).toHaveProperty('type', 'object')
      expect(result?.schema).toHaveProperty('properties')
      expect(result?.schema.properties).toHaveProperty('summary')
      expect(result?.schema.properties).toHaveProperty('topics')
      expect(result?.schema.properties).toHaveProperty('sentiment')
      expect(result?.schema.required).toContain('summary')
      expect(result?.schema.required).toContain('topics')
    })

    it('should return null for Anthropic span without tools', () => {
      const span = createSpanWithoutSchema('anthropic')
      const result = detectAnthropicJsonSchema(span)

      expect(result).toBeNull()
    })

    it('should return null for non-Anthropic span', () => {
      const span = createOpenAISpanWithSchema()
      const result = detectAnthropicJsonSchema(span)

      expect(result).toBeNull()
    })
  })

  describe('detectGeminiJsonSchema', () => {
    it('should detect JSON schema from Gemini span with response_json_schema', () => {
      const span = createGeminiSpanWithSchema()
      const result = detectGeminiJsonSchema(span)

      expect(result).not.toBeNull()
      expect(result?.schema).toHaveProperty('type', 'object')
      expect(result?.schema).toHaveProperty('properties')
      expect(result?.schema.properties).toHaveProperty('title')
      expect(result?.schema.properties).toHaveProperty('content')
      expect(result?.schema.properties).toHaveProperty('tags')
      expect(result?.schema.required).toContain('title')
      expect(result?.schema.required).toContain('content')
    })

    it('should return null for Gemini span without JSON schema', () => {
      const span = createSpanWithoutSchema('google')
      const result = detectGeminiJsonSchema(span)

      expect(result).toBeNull()
    })

    it('should return null for non-Gemini span', () => {
      const span = createOpenAISpanWithSchema()
      const result = detectGeminiJsonSchema(span)

      expect(result).toBeNull()
    })

    it('should handle "gemini" provider name (in addition to "google")', () => {
      const span = createGeminiSpanWithSchema()
      span.attributes_json['llm.provider'] = 'gemini'
      const result = detectGeminiJsonSchema(span)

      expect(result).not.toBeNull()
      expect(result?.schema).toHaveProperty('type', 'object')
    })
  })

  describe('detectJsonSchema (unified detector)', () => {
    it('should detect OpenAI schema', () => {
      const span = createOpenAISpanWithSchema()
      const result = detectJsonSchema(span)

      expect(result).not.toBeNull()
      expect(result).toHaveProperty('type', 'object')
      expect(result?.properties).toHaveProperty('name')
    })

    it('should detect Anthropic schema', () => {
      const span = createAnthropicSpanWithSchema()
      const result = detectJsonSchema(span)

      expect(result).not.toBeNull()
      expect(result).toHaveProperty('type', 'object')
      expect(result?.properties).toHaveProperty('summary')
    })

    it('should detect Gemini schema', () => {
      const span = createGeminiSpanWithSchema()
      const result = detectJsonSchema(span)

      expect(result).not.toBeNull()
      expect(result).toHaveProperty('type', 'object')
      expect(result?.properties).toHaveProperty('title')
    })

    it('should return null when no schema is present', () => {
      const span = createSpanWithoutSchema('openai')
      const result = detectJsonSchema(span)

      expect(result).toBeNull()
    })
  })

  describe('Edge cases and robustness', () => {
    it('should handle invocation_parameters as object instead of string', () => {
      const span = createOpenAISpanWithSchema()
      // Parse the JSON string to object
      span.attributes_json['llm.invocation_parameters'] = JSON.parse(
        span.attributes_json['llm.invocation_parameters'] as string,
      )

      const result = detectOpenAIJsonSchema(span)
      expect(result).not.toBeNull()
      expect(result?.schema).toHaveProperty('type', 'object')
    })

    it('should handle malformed JSON gracefully', () => {
      const span = createOpenAISpanWithSchema()
      span.attributes_json['llm.invocation_parameters'] = 'invalid json {'

      const result = detectOpenAIJsonSchema(span)
      expect(result).toBeNull()
    })

    it('should handle missing invocation_parameters', () => {
      const span = createOpenAISpanWithSchema()
      delete span.attributes_json['llm.invocation_parameters']

      const result = detectOpenAIJsonSchema(span)
      expect(result).toBeNull()
    })

    it('should handle empty tools array for Anthropic', () => {
      const span = createAnthropicSpanWithSchema()
      span.attributes_json['llm.invocation_parameters'] = JSON.stringify({
        temperature: 0.5,
        max_tokens: 4096,
        tools: [],
      })

      const result = detectAnthropicJsonSchema(span)
      expect(result).toBeNull()
    })
  })
})

import { describe, it, expect } from 'vitest'
import { ensureOpenAISchemaCompatibility } from './schema-utils'

describe('ensureOpenAISchemaCompatibility', () => {
  describe('required field handling', () => {
    it('should add required field with all property keys for simple object', () => {
      const schema = {
        type: 'object',
        properties: {
          name: { type: 'string' },
          age: { type: 'number' },
        },
      }

      const result = ensureOpenAISchemaCompatibility(schema)

      expect(result.required).toEqual(['name', 'age'])
      expect(result.additionalProperties).toBe(false)
    })

    it('should add required field recursively for nested objects', () => {
      const schema = {
        type: 'object',
        properties: {
          user: {
            type: 'object',
            properties: {
              name: { type: 'string' },
              email: { type: 'string' },
            },
          },
          metadata: {
            type: 'object',
            properties: {
              created_at: { type: 'string' },
            },
          },
        },
      }

      const result = ensureOpenAISchemaCompatibility(schema)

      // Root object should have required
      expect(result.required).toEqual(['user', 'metadata'])
      expect(result.additionalProperties).toBe(false)

      // Nested user object should have required
      expect(result.properties.user.required).toEqual(['name', 'email'])
      expect(result.properties.user.additionalProperties).toBe(false)

      // Nested metadata object should have required
      expect(result.properties.metadata.required).toEqual(['created_at'])
      expect(result.properties.metadata.additionalProperties).toBe(false)
    })

    it('should not add required field for objects without properties', () => {
      const schema = {
        type: 'object',
        additionalProperties: {
          type: 'string',
        },
      }

      const result = ensureOpenAISchemaCompatibility(schema)

      expect(result.required).toBeUndefined()
      // additionalProperties schema is a primitive type (string), so it stays as-is
      expect(result.additionalProperties).toEqual({ type: 'string' })
    })

    it('should not add required field for empty properties', () => {
      const schema = {
        type: 'object',
        properties: {},
      }

      const result = ensureOpenAISchemaCompatibility(schema)

      expect(result.required).toBeUndefined()
      expect(result.additionalProperties).toBe(false)
    })

    it('should handle array items with object schemas', () => {
      const schema = {
        type: 'object',
        properties: {
          items: {
            type: 'array',
            items: {
              type: 'object',
              properties: {
                id: { type: 'string' },
                value: { type: 'number' },
              },
            },
          },
        },
      }

      const result = ensureOpenAISchemaCompatibility(schema)

      // Root object should have required
      expect(result.required).toEqual(['items'])

      // Array items should have required
      expect(result.properties.items.items.required).toEqual(['id', 'value'])
      expect(result.properties.items.items.additionalProperties).toBe(false)
    })

    it('should handle oneOf with object schemas', () => {
      const schema = {
        type: 'object',
        properties: {
          response: {
            oneOf: [
              {
                type: 'object',
                properties: {
                  success: { type: 'boolean' },
                  data: { type: 'string' },
                },
              },
              {
                type: 'object',
                properties: {
                  error: { type: 'string' },
                },
              },
            ],
          },
        },
      }

      const result = ensureOpenAISchemaCompatibility(schema)

      // Root object should have required
      expect(result.required).toEqual(['response'])

      // First oneOf option should have required
      expect(result.properties.response.oneOf[0].required).toEqual(['success', 'data'])
      expect(result.properties.response.oneOf[0].additionalProperties).toBe(false)

      // Second oneOf option should have required
      expect(result.properties.response.oneOf[1].required).toEqual(['error'])
      expect(result.properties.response.oneOf[1].additionalProperties).toBe(false)
    })

    it('should handle real-world Gemini schema from telemetry', () => {
      const schema = {
        type: 'object',
        properties: {
          split_log_entries: {
            default: [],
            items: {
              type: 'string',
            },
            title: 'Split Log Entries',
            type: 'array',
          },
        },
        title: 'SplitActivityQueriesGeminiSchema',
        additionalProperties: false,
      }

      const result = ensureOpenAISchemaCompatibility(schema)

      // Root object should have required field
      expect(result.required).toEqual(['split_log_entries'])
      expect(result.additionalProperties).toBe(false)
    })
  })

  describe('additionalProperties handling', () => {
    it('should add additionalProperties: false to all object types', () => {
      const schema = {
        type: 'object',
        properties: {
          name: { type: 'string' },
        },
      }

      const result = ensureOpenAISchemaCompatibility(schema)

      expect(result.additionalProperties).toBe(false)
    })

    it('should preserve existing additionalProperties if it is false', () => {
      const schema = {
        type: 'object',
        properties: {
          name: { type: 'string' },
        },
        additionalProperties: false,
      }

      const result = ensureOpenAISchemaCompatibility(schema)

      expect(result.additionalProperties).toBe(false)
    })

    it('should process additionalProperties if it is an object schema', () => {
      const schema = {
        type: 'object',
        additionalProperties: {
          type: 'object',
          properties: {
            value: { type: 'string' },
          },
        },
      }

      const result = ensureOpenAISchemaCompatibility(schema)

      // The additionalProperties schema is an object type, so it should get
      // additionalProperties: false and required: ['value']
      expect(result.additionalProperties.additionalProperties).toBe(false)
      expect(result.additionalProperties.required).toEqual(['value'])
    })
  })

  describe('immutability', () => {
    it('should not mutate the original schema', () => {
      const original = {
        type: 'object',
        properties: {
          name: { type: 'string' },
          age: { type: 'number' },
        },
      }

      const originalCopy = JSON.parse(JSON.stringify(original))
      ensureOpenAISchemaCompatibility(original)

      // Original should remain unchanged
      expect(original).toEqual(originalCopy)
      expect((original as any).required).toBeUndefined()
      expect((original as any).additionalProperties).toBeUndefined()
    })
  })

  describe('edge cases', () => {
    it('should handle null values gracefully', () => {
      const schema = {
        type: 'object',
        properties: {
          nullable_field: { type: 'string', nullable: true },
        },
      }

      const result = ensureOpenAISchemaCompatibility(schema)

      expect(result.required).toEqual(['nullable_field'])
    })

    it('should handle deeply nested structures', () => {
      const schema = {
        type: 'object',
        properties: {
          level1: {
            type: 'object',
            properties: {
              level2: {
                type: 'object',
                properties: {
                  level3: {
                    type: 'object',
                    properties: {
                      value: { type: 'string' },
                    },
                  },
                },
              },
            },
          },
        },
      }

      const result = ensureOpenAISchemaCompatibility(schema)

      expect(result.required).toEqual(['level1'])
      expect(result.properties.level1.required).toEqual(['level2'])
      expect(result.properties.level1.properties.level2.required).toEqual(['level3'])
      expect(result.properties.level1.properties.level2.properties.level3.required).toEqual([
        'value',
      ])
    })

    it('should handle arrays with tuple validation (array of schemas)', () => {
      const schema = {
        type: 'object',
        properties: {
          tuple: {
            type: 'array',
            items: [
              {
                type: 'object',
                properties: { name: { type: 'string' } },
              },
              {
                type: 'object',
                properties: { value: { type: 'number' } },
              },
            ],
          },
        },
      }

      const result = ensureOpenAISchemaCompatibility(schema)

      expect(result.properties.tuple.items[0].required).toEqual(['name'])
      expect(result.properties.tuple.items[1].required).toEqual(['value'])
    })

    it('should handle definitions/$defs', () => {
      const schema = {
        type: 'object',
        properties: {
          data: { $ref: '#/$defs/DataObject' },
        },
        $defs: {
          DataObject: {
            type: 'object',
            properties: {
              id: { type: 'string' },
              name: { type: 'string' },
            },
          },
        },
      }

      const result = ensureOpenAISchemaCompatibility(schema)

      expect(result.$defs.DataObject.required).toEqual(['id', 'name'])
      expect(result.$defs.DataObject.additionalProperties).toBe(false)
    })
  })
})

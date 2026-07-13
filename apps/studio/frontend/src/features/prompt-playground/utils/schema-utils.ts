/**
 * Utility functions for JSON Schema manipulation across LLM providers
 */

export type JsonSchema = Record<string, unknown>

type ExistingAdditionalProperties<T> = T extends { additionalProperties: infer Value }
  ? OpenAICompatibleSchema<Value>
  : boolean | JsonSchema | undefined

export type OpenAICompatibleSchema<T> = T extends readonly (infer Item)[]
  ? OpenAICompatibleSchema<Item>[]
  : T extends JsonSchema
    ? Omit<
        { [Key in keyof T]: OpenAICompatibleSchema<T[Key]> },
        'additionalProperties' | 'required'
      > & {
        additionalProperties: ExistingAdditionalProperties<T>
        required: string[] | undefined
      }
    : T

function isJsonSchema(value: unknown): value is JsonSchema {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

/**
 * Ensures a JSON schema is compatible with OpenAI's strict mode by adding
 * `additionalProperties: false` and `required` fields to all object types recursively.
 *
 * OpenAI's strict structured outputs require that every object in the schema:
 * 1. Explicitly sets `additionalProperties: false`
 * 2. Has a `required` array containing all property keys
 *
 * Other providers (Gemini, Anthropic) don't have these requirements, so schemas
 * from those providers need transformation.
 *
 * @param schema - The original JSON schema (not modified)
 * @returns A new schema with OpenAI strict mode requirements applied
 */
export function ensureOpenAISchemaCompatibility<T extends JsonSchema>(
  schema: T,
): OpenAICompatibleSchema<T> {
  // Deep clone to avoid mutating the original
  const cloned = JSON.parse(JSON.stringify(schema)) as JsonSchema

  function addAdditionalPropertiesRecursive(obj: unknown): void {
    if (!isJsonSchema(obj)) {
      return
    }

    // If this is an object type definition, ensure additionalProperties is false
    // and required contains all property keys
    if (obj.type === 'object') {
      // Add required field with all property keys
      if (isJsonSchema(obj.properties)) {
        const propertyKeys = Object.keys(obj.properties)
        if (propertyKeys.length > 0) {
          // Only set required if there are properties
          obj.required = propertyKeys
        }

        // Recursively process properties
        for (const property of Object.values(obj.properties)) {
          addAdditionalPropertiesRecursive(property)
        }
      }

      // Handle patternProperties if present
      if (isJsonSchema(obj.patternProperties)) {
        for (const patternSchema of Object.values(obj.patternProperties)) {
          addAdditionalPropertiesRecursive(patternSchema)
        }
      }

      // Handle additionalProperties:
      // - If it's a schema object, process it recursively (don't overwrite it)
      // - Otherwise, ensure it's set to false
      if (isJsonSchema(obj.additionalProperties)) {
        addAdditionalPropertiesRecursive(obj.additionalProperties)
      } else if (obj.additionalProperties === undefined) {
        obj.additionalProperties = false
      }
    }

    // Handle array items
    if (obj.type === 'array') {
      if (obj.items) {
        if (Array.isArray(obj.items)) {
          // Tuple validation
          obj.items.forEach((item) => addAdditionalPropertiesRecursive(item))
        } else {
          // Single schema for all items
          addAdditionalPropertiesRecursive(obj.items)
        }
      }

      // Handle prefixItems (JSON Schema 2020-12)
      if (obj.prefixItems && Array.isArray(obj.prefixItems)) {
        obj.prefixItems.forEach((item) => addAdditionalPropertiesRecursive(item))
      }
    }

    // Handle oneOf, anyOf, allOf
    ['oneOf', 'anyOf', 'allOf'].forEach((keyword) => {
      const schemas = obj[keyword]
      if (Array.isArray(schemas)) {
        schemas.forEach((subSchema) => addAdditionalPropertiesRecursive(subSchema))
      }
    })

    // Handle not
    if (obj.not) {
      addAdditionalPropertiesRecursive(obj.not)
    }

    // Handle definitions/defs (common places for reusable schemas)
    ['definitions', '$defs'].forEach((keyword) => {
      const definitions = obj[keyword]
      if (isJsonSchema(definitions)) {
        for (const definition of Object.values(definitions)) {
          addAdditionalPropertiesRecursive(definition)
        }
      }
    })
  }

  addAdditionalPropertiesRecursive(cloned)
  return cloned as OpenAICompatibleSchema<T>
}

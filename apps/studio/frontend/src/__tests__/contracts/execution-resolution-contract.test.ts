import { describe, expect, it } from 'vitest'
import { z } from 'zod'
import openapiSpec from '../../../backend/openapi.json'

const ParameterSchema = z.object({
  name: z.string(),
  in: z.literal('query'),
  required: z.boolean(),
  schema: z.record(z.unknown()),
}).passthrough()

const ResolutionOperationSchema = z.object({
  operationId: z.literal('resolve_execution'),
  parameters: z.array(ParameterSchema),
  responses: z.record(z.unknown()),
}).passthrough()

const ResolutionSurfaceSchema = z.object({
  paths: z.object({
    '/api/v1/execution-resolution': z.object({ get: ResolutionOperationSchema }).passthrough(),
  }).passthrough(),
}).passthrough()

describe('API Contract: execution resolution', () => {
  const operation = ResolutionSurfaceSchema.parse(openapiSpec)
    .paths['/api/v1/execution-resolution'].get

  it('requires one exact service-scoped executable identity', () => {
    expect(operation.parameters.map((parameter) => parameter.name)).toEqual([
      'service_namespace',
      'service_name',
      'executable_type',
      'runtime_id',
    ])
    expect(operation.parameters.every((parameter) => parameter.required)).toBe(true)
    expect(operation.parameters.find((parameter) => parameter.name === 'executable_type')).toMatchObject({
      schema: { enum: ['workflow', 'subflow', 'agent'] },
    })
  })

  it('publishes exact success, conflict, not-found, and validation contracts', () => {
    expect(operation.responses['200']).toMatchObject({
      content: {
        'application/json': {
          schema: { $ref: '#/components/schemas/ExecutionResolution' },
        },
      },
    })
    expect(operation.responses['404']).toMatchObject({
      description: 'Execution owner span not found',
    })
    expect(operation.responses['409']).toMatchObject({
      content: {
        'application/json': {
          schema: { $ref: '#/components/schemas/ExecutionResolutionConflictResponse' },
        },
      },
    })
    expect(operation.responses['422']).toMatchObject({
      content: {
        'application/json': {
          schema: { $ref: '#/components/schemas/HTTPValidationError' },
        },
      },
    })
  })
})

import { describe, expect, it } from 'vitest'
import { z } from 'zod'
import openapiSpec from '../../../backend/openapi.json'
import { generateMock } from '../../auth/test-utils/openapi-mock-generator'
import {
  EvaluationTokenCreatedSchema,
  EvaluationTokenListSchema,
  EvaluationTokenReadSchema,
} from '../../features/evaluation-tokens/schemas'

const ParameterSchema = z
  .object({
    name: z.string(),
    in: z.enum(['query', 'path']),
    required: z.boolean(),
    schema: z.record(z.unknown()),
  })
  .passthrough()

const OperationSchema = z
  .object({
    operationId: z.string(),
    parameters: z.array(ParameterSchema).default([]),
    responses: z.record(z.unknown()),
  })
  .passthrough()

const EvaluationTokenSurfaceSchema = z
  .object({
    paths: z
      .object({
        '/api/v1/evaluation-tokens': z
          .object({
            get: OperationSchema,
            post: OperationSchema,
          })
          .passthrough(),
        '/api/v1/evaluation-tokens/{token_id}/revoke': z
          .object({ put: OperationSchema })
          .passthrough(),
      })
      .passthrough(),
  })
  .passthrough()

describe('API Contract: evaluation tokens', () => {
  const surface = EvaluationTokenSurfaceSchema.parse(openapiSpec)
  const collection = surface.paths['/api/v1/evaluation-tokens']
  const revoke =
    surface.paths['/api/v1/evaluation-tokens/{token_id}/revoke'].put

  it('publishes create-once, bounded list, and explicit revoke operations', () => {
    expect(collection.post.operationId).toBe('create_evaluation_token')
    expect(collection.post.responses['201']).toMatchObject({
      content: {
        'application/json': {
          schema: { $ref: '#/components/schemas/EvaluationTokenCreated' },
        },
      },
    })

    expect(collection.get.operationId).toBe('list_evaluation_tokens')
    expect(collection.get.parameters.map((parameter) => parameter.name)).toEqual([
      'cursor',
      'limit',
    ])
    expect(
      collection.get.parameters.find((parameter) => parameter.name === 'limit'),
    ).toMatchObject({
      schema: { default: 50, maximum: 100, minimum: 1 },
    })

    expect(revoke.operationId).toBe('revoke_evaluation_token')
    expect(revoke.parameters).toMatchObject([
      {
        name: 'token_id',
        in: 'path',
        required: true,
      },
    ])
  })

  it('keeps the token secret on create responses only', () => {
    const schemas = openapiSpec.components.schemas
    expect(schemas.EvaluationTokenCreated.properties).toHaveProperty('token')
    expect(schemas.EvaluationTokenRead.properties).not.toHaveProperty('token')
    expect(JSON.stringify(schemas.EvaluationTokenRead)).not.toContain('secret_hash')
  })

  it('parses OpenAPI-generated responses with strict frontend schemas', () => {
    const created = generateMock('create_evaluation_token').mock as Record<
      string,
      unknown
    >
    const prefix = 'junjo_eval_AbCdEfGhIjKl'
    expect(
      EvaluationTokenCreatedSchema.parse(
        {
          ...created,
          // openapi-backend does not honor OpenAPI 3.1 string examples when a
          // regex contains both a literal dot and bounded URL-safe segments.
          prefix,
          token:
            'junjo_eval_AbCdEfGhIjKl.0123456789_abcdefghijklmnopqrstuv-wxyzABCDE',
        },
      ),
    ).toBeDefined()
    const list = generateMock('list_evaluation_tokens').mock as {
      items: Array<Record<string, unknown>>
    }
    expect(
      EvaluationTokenListSchema.parse({
        ...list,
        items: list.items.map((item) => ({ ...item, prefix })),
      }),
    ).toBeDefined()
    expect(
      EvaluationTokenReadSchema.parse({
        ...(generateMock('revoke_evaluation_token').mock as Record<
          string,
          unknown
        >),
        prefix,
      }),
    ).toBeDefined()
  })
})

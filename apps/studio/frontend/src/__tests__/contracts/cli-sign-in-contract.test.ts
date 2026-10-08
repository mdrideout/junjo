import { describe, expect, it } from 'vitest'
import { z } from 'zod'
import openapiSpec from '../../../backend/openapi.json'
import { UserResponseSchema } from '../../auth/response-schemas'
import { generateMock } from '../../auth/test-utils/openapi-mock-generator'
import {
  CliSignInApprovedSchema,
  CliSignInReadSchema,
} from '../../features/cli-sign-in/schemas'
import { EvaluationTokenScopeSchema } from '../../features/evaluation-tokens/schemas'

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
    parameters: z.array(ParameterSchema),
    responses: z.record(z.unknown()),
  })
  .passthrough()

const CliSignInSurfaceSchema = z
  .object({
    paths: z
      .object({
        '/api/v1/cli-sign-ins/{user_code}': z.object({ get: OperationSchema }).passthrough(),
        '/api/v1/cli-sign-ins/{user_code}/approve': z
          .object({ post: OperationSchema })
          .passthrough(),
        '/api/v1/cli-sign-ins/{user_code}/deny': z
          .object({ post: OperationSchema })
          .passthrough(),
      })
      .passthrough(),
  })
  .passthrough()

function jsonBody(schema: string) {
  return { content: { 'application/json': { schema: { $ref: schema } } } }
}

describe('API Contract: CLI sign-in approval', () => {
  const surface = CliSignInSurfaceSchema.parse(openapiSpec)
  const read = surface.paths['/api/v1/cli-sign-ins/{user_code}'].get
  const approve = surface.paths['/api/v1/cli-sign-ins/{user_code}/approve'].post
  const deny = surface.paths['/api/v1/cli-sign-ins/{user_code}/deny'].post
  const schemas = openapiSpec.components.schemas

  it('publishes the read, approve, and deny operations by string user code', () => {
    expect(read.operationId).toBe('get_cli_sign_in')
    expect(approve.operationId).toBe('approve_cli_sign_in')
    expect(deny.operationId).toBe('deny_cli_sign_in')

    for (const operation of [read, approve, deny]) {
      expect(operation.parameters).toMatchObject([
        {
          name: 'user_code',
          in: 'path',
          required: true,
          schema: { type: 'string' },
        },
      ])
    }
  })

  it('takes no request body to approve or deny', () => {
    expect(approve).not.toHaveProperty('requestBody')
    expect(deny).not.toHaveProperty('requestBody')
  })

  it('publishes the body of each success response', () => {
    expect(read.responses['200']).toMatchObject(jsonBody('#/components/schemas/CliSignInRead'))
    expect(approve.responses['200']).toMatchObject(
      jsonBody('#/components/schemas/CliSignInApproved'),
    )
    expect(deny.responses['200']).toMatchObject(jsonBody('#/components/schemas/UserResponse'))
  })

  it('answers a missing session, an unknown code, and a malformed code with the one error body', () => {
    for (const operation of [read, approve, deny]) {
      for (const status of ['401', '404', '422']) {
        expect(operation.responses[status]).toMatchObject(
          jsonBody('#/components/schemas/ErrorResponse'),
        )
      }
    }
    expect(schemas.ErrorResponse.required).toEqual(['code', 'message'])
  })

  it('publishes exactly the fields the frontend schemas read, all of them required', () => {
    const readFields = Object.keys(CliSignInReadSchema.shape).sort()
    expect(Object.keys(schemas.CliSignInRead.properties).sort()).toEqual(readFields)
    expect([...schemas.CliSignInRead.required].sort()).toEqual(readFields)

    const approvedFields = Object.keys(CliSignInApprovedSchema.shape).sort()
    expect(Object.keys(schemas.CliSignInApproved.properties).sort()).toEqual(approvedFields)
    expect([...schemas.CliSignInApproved.required].sort()).toEqual(approvedFields)

    const deniedFields = Object.keys(UserResponseSchema.shape).sort()
    expect(Object.keys(schemas.UserResponse.properties).sort()).toEqual(deniedFields)
    expect([...schemas.UserResponse.required].sort()).toEqual(deniedFields)
  })

  it('requests only the developer token scopes the frontend can describe', () => {
    expect(schemas.CliSignInRead.properties.scopes.items).toEqual({
      $ref: '#/components/schemas/EvaluationTokenScope',
    })
    expect(schemas.EvaluationTokenScope.enum).toEqual(EvaluationTokenScopeSchema.options)
  })

  it('parses OpenAPI-generated responses with the strict frontend schemas', () => {
    expect(CliSignInReadSchema.parse(generateMock('get_cli_sign_in').mock)).toBeDefined()
    expect(
      CliSignInApprovedSchema.parse(generateMock('approve_cli_sign_in').mock),
    ).toBeDefined()
    expect(UserResponseSchema.parse(generateMock('deny_cli_sign_in').mock)).toBeDefined()
  })
})

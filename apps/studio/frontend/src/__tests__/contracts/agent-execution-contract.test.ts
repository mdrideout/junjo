import { describe, expect, it } from 'vitest'
import { z } from 'zod'
import openapiSpec from '../../../backend/openapi.json'

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

const AgentOpenApiSurfaceSchema = z
  .object({
    paths: z
      .object({
        '/api/v1/agent-executions': z.object({ get: OperationSchema }).passthrough(),
        '/api/v1/agent-executions/{trace_id}/{agent_span_id}': z
          .object({ get: OperationSchema })
          .passthrough(),
        '/api/v1/workflow-executions/{trace_id}/{workflow_span_id}/store': z
          .object({ get: OperationSchema })
          .passthrough(),
      })
      .passthrough(),
  })
  .passthrough()

describe('API Contract: Agent execution routes', () => {
  const surface = AgentOpenApiSurfaceSchema.parse(openapiSpec)
  const listOperation = surface.paths['/api/v1/agent-executions'].get
  const detailOperation =
    surface.paths['/api/v1/agent-executions/{trace_id}/{agent_span_id}'].get
  const workflowStoreOperation =
    surface.paths['/api/v1/workflow-executions/{trace_id}/{workflow_span_id}/store'].get

  function expectSeparatedErrorContracts(
    operation: z.infer<typeof OperationSchema>,
    semanticSchema: string,
  ) {
    expect(operation.responses['409']).toMatchObject({
      content: {
        'application/json': {
          schema: { $ref: semanticSchema },
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
  }

  it('publishes the service-scoped list operation and every supported filter', () => {
    expect(listOperation.operationId).toBe('list_agent_executions')
    expect(listOperation.parameters.map((parameter) => parameter.name)).toEqual([
      'service_namespace',
      'service_name',
      'agent_key',
      'structural_id',
      'service_version',
      'outcome',
      'start_time',
      'end_time',
      'limit',
    ])
    expect(listOperation.parameters.find((parameter) => parameter.name === 'service_namespace')).toMatchObject({
      in: 'query',
      required: true,
    })
    expect(listOperation.parameters.find((parameter) => parameter.name === 'service_name')).toMatchObject({
      in: 'query',
      required: true,
      schema: { minLength: 1 },
    })
    expect(listOperation.responses['200']).toMatchObject({
      content: {
        'application/json': {
          schema: {
            type: 'array',
            items: { $ref: '#/components/schemas/AgentExecutionSummary' },
          },
        },
      },
    })
    expectSeparatedErrorContracts(
      listOperation,
      '#/components/schemas/AgentEvidenceErrorResponse',
    )
  })

  it('publishes canonical trace/span detail identity and typed evidence errors', () => {
    expect(detailOperation.operationId).toBe('get_agent_execution_detail')
    expect(detailOperation.parameters).toMatchObject([
      {
        name: 'trace_id',
        in: 'path',
        required: true,
        schema: { pattern: '^[0-9a-f]{32}$' },
      },
      {
        name: 'agent_span_id',
        in: 'path',
        required: true,
        schema: { pattern: '^[0-9a-f]{16}$' },
      },
    ])
    expect(detailOperation.responses['200']).toMatchObject({
      content: {
        'application/json': {
          schema: { $ref: '#/components/schemas/AgentExecutionDetail' },
        },
      },
    })
    expectSeparatedErrorContracts(
      detailOperation,
      '#/components/schemas/AgentEvidenceErrorResponse',
    )
    expectSeparatedErrorContracts(
      workflowStoreOperation,
      '#/components/schemas/WorkflowEvidenceErrorResponse',
    )
  })
})

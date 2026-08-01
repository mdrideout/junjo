import { describe, expect, it } from 'vitest'
import { z } from 'zod'
import openapiSpec from '../../../backend/openapi.json'
import { generateMock } from '../../auth/test-utils/openapi-mock-generator'
import {
  EvaluationDatasetDetailSchema,
  EvaluationRunDetailSchema,
  EvaluationRunListPageSchema,
} from '../../features/evaluation-runs/schemas/evaluation-runs'

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

const EvaluationRunsSurfaceSchema = z
  .object({
    paths: z
      .object({
        '/api/v1/evaluation/datasets/{dataset_id}': z.object({ get: OperationSchema }).passthrough(),
        '/api/v1/evaluation/runs': z.object({ get: OperationSchema }).passthrough(),
        '/api/v1/evaluation/runs/{run_id}': z.object({ get: OperationSchema }).passthrough(),
      })
      .passthrough(),
  })
  .passthrough()

describe('API Contract: evaluation run reads', () => {
  const surface = EvaluationRunsSurfaceSchema.parse(openapiSpec)
  const datasetDetailOperation =
    surface.paths['/api/v1/evaluation/datasets/{dataset_id}'].get
  const listOperation = surface.paths['/api/v1/evaluation/runs'].get
  const detailOperation = surface.paths['/api/v1/evaluation/runs/{run_id}'].get

  it('publishes a bounded cursor-paginated run list', () => {
    expect(listOperation.operationId).toBe('list_evaluation_runs')
    expect(listOperation.parameters.map((parameter) => parameter.name)).toEqual([
      'dataset_id',
      'target_kind',
      'target_key',
      'input_version',
      'evaluation_name',
      'cursor',
      'limit',
    ])
    expect(listOperation.parameters.every((parameter) => !parameter.required)).toBe(true)
    expect(listOperation.parameters.find((parameter) => parameter.name === 'limit')).toMatchObject({
      schema: { default: 50, maximum: 100, minimum: 1 },
    })
    expect(listOperation.responses['200']).toMatchObject({
      content: {
        'application/json': {
          schema: { $ref: '#/components/schemas/EvaluationRunList' },
        },
      },
    })
  })

  it('publishes one evidence-free run detail document', () => {
    expect(detailOperation.operationId).toBe('get_evaluation_run')
    expect(detailOperation.parameters).toMatchObject([
      {
        name: 'run_id',
        in: 'path',
        required: true,
      },
    ])
    expect(detailOperation.responses['200']).toMatchObject({
      content: {
        'application/json': {
          schema: { $ref: '#/components/schemas/EvaluationRunDetail' },
        },
      },
    })
  })

  it('parses the OpenAPI-generated dataset detail with the strict frontend schema', () => {
    expect(datasetDetailOperation.operationId).toBe('get_evaluation_dataset')
    const { mock } = generateMock('get_evaluation_dataset')
    expect(EvaluationDatasetDetailSchema.parse(mock)).toBeDefined()
  })

  it('parses the OpenAPI-generated run list with the strict frontend schema', () => {
    const { mock } = generateMock('list_evaluation_runs')

    expect(EvaluationRunListPageSchema.parse(mock)).toBeDefined()
  })

  it('parses the OpenAPI-generated run detail with the strict frontend schema', () => {
    const { mock } = generateMock('get_evaluation_run')

    expect(EvaluationRunDetailSchema.parse(mock)).toBeDefined()
  })
})

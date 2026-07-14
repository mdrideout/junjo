import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'
import { BackendWorkflowStoreProjectionFixtureListSchema } from '../schemas/workflow-store-diagnostic'

const testDirectory = path.dirname(fileURLToPath(import.meta.url))
const projectionPath = path.join(testDirectory, 'workflow-store-projections.json')

describe('API Contract: backend Workflow Store projections', () => {
  it('strictly parses every canonical Workflow and Subflow owner projection', () => {
    const projections = BackendWorkflowStoreProjectionFixtureListSchema.parse(
      JSON.parse(fs.readFileSync(projectionPath, 'utf8')),
    )

    expect(projections).toHaveLength(7)
    expect(new Set(projections.map((projection) => projection.case_name)).size).toBe(7)
    for (const projection of projections) {
      expect(projection.detail.state.reconstruction_status).toBe('verified')
      expect(projection.detail.state.reconstructable).toBe(true)
      expect(projection.detail.integrity.status).toBe('complete')
    }
  })
})

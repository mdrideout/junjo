import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { BackendWorkflowStoreProjectionFixtureListSchema } from '../schemas/workflow-store-diagnostic'
import { WorkflowStoreDiagnosticsNotice } from './WorkflowStoreDiagnosticsNotice'

const projectionPath = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  '../testing/workflow-store-projections.json',
)

function loadHealthyDiagnostic() {
  const projections = BackendWorkflowStoreProjectionFixtureListSchema.parse(
    JSON.parse(fs.readFileSync(projectionPath, 'utf8')),
  )
  const projection = projections.find(
    (candidate) => candidate.case_name === 'basic_workflow_success:1111111111111111',
  )
  if (projection === undefined) throw new Error('Workflow projection missing')
  return structuredClone(projection.detail)
}

describe('WorkflowStoreDiagnosticsNotice', () => {
  it('is silent for complete, verified state history', () => {
    const { container } = render(
      <WorkflowStoreDiagnosticsNotice
        diagnostic={loadHealthyDiagnostic()}
        loading={false}
        error={null}
        ownerIdentified
      />,
    )

    expect(container).toBeEmptyDOMElement()
  })

  it('distinguishes payload policy from corruption', () => {
    const diagnostic = loadHealthyDiagnostic()
    diagnostic.state.reconstructable = false
    diagnostic.state.reconstruction_status = 'policy_unavailable'
    diagnostic.state.reconstruction_reason = 'payload_excluded'

    render(
      <WorkflowStoreDiagnosticsNotice
        diagnostic={diagnostic}
        loading={false}
        error={null}
        ownerIdentified
      />,
    )

    expect(screen.getByRole('status')).toHaveTextContent('unavailable by payload policy')
    expect(screen.getByText(/does not indicate execution failure or telemetry corruption/))
      .toBeInTheDocument()
  })

  it('warns when replay fails and exposes technical details on demand', () => {
    const diagnostic = loadHealthyDiagnostic()
    diagnostic.state.reconstructable = false
    diagnostic.state.reconstruction_status = 'failed'
    diagnostic.state.reconstruction_reason = 'patch_replay_mismatch'
    diagnostic.integrity.status = 'partial'

    render(
      <WorkflowStoreDiagnosticsNotice
        diagnostic={diagnostic}
        loading={false}
        error={null}
        ownerIdentified
      />,
    )

    expect(screen.getByRole('alert')).toHaveTextContent('State history could not be verified')
    expect(screen.getByText('Technical diagnostics')).toBeInTheDocument()
  })
})

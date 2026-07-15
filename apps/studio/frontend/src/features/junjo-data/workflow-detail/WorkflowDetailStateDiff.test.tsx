import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { configureStore } from '@reduxjs/toolkit'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Provider } from 'react-redux'
import { BrowserRouter } from 'react-router'
import { beforeAll, describe, expect, it, vi } from 'vitest'
import { loadJunjoTransportFixtureCase } from '../../../test-utils/junjo-fixture-loader'
import { OtelSpan, OtelSpanSchema } from '../../traces/schemas/schemas'
import tracesSlice from '../../traces/store/slice'
import workflowDetailSlice from './store/slice'
import { spanSelection } from './store/slice'
import { makeTraceEvidence } from '../../traces/testing/make-trace-evidence'
import WorkflowDetailStateDiff from './WorkflowDetailStateDiff'
import {
  BackendWorkflowStoreProjectionFixtureListSchema,
  type WorkflowStoreDiagnostic,
} from '../../workflow-executions/schemas/workflow-store-diagnostic'

const testDirectory = path.dirname(fileURLToPath(import.meta.url))
const workflowProjectionPath = path.resolve(
  testDirectory,
  '../../workflow-executions/testing/workflow-store-projections.json',
)

function loadBasicWorkflowProjection(): WorkflowStoreDiagnostic {
  const projections = BackendWorkflowStoreProjectionFixtureListSchema.parse(
    JSON.parse(fs.readFileSync(workflowProjectionPath, 'utf8')),
  )
  const projection = projections.find(
    (candidate) => candidate.case_name === 'basic_workflow_success:1111111111111111',
  )
  if (projection === undefined) throw new Error('Basic Workflow projection missing')
  return structuredClone(projection.detail)
}

beforeAll(() => {
  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    value: vi.fn().mockImplementation((query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })),
  })
})

function loadFixtureSpans(caseName: string): OtelSpan[] {
  const fixture = loadJunjoTransportFixtureCase(caseName)
  return OtelSpanSchema.array().parse(fixture.spans)
}

function renderStateDiff({
  spans,
  activeSpan,
  defaultWorkflowSpan,
  diagnostic,
}: {
  spans: OtelSpan[]
  activeSpan: OtelSpan
  defaultWorkflowSpan: OtelSpan
  diagnostic: WorkflowStoreDiagnostic
}) {
  const store = configureStore({
    reducer: {
      workflowDetailState: workflowDetailSlice,
      tracesState: tracesSlice,
    },
    preloadedState: {
      workflowDetailState: {
        activeSpanIdentity: spanSelection(activeSpan),
        activeStateEvent: null,
        stateEventScrollTarget: null,
        openFailuresTrigger: null,
      },
      tracesState: {
        serviceNames: {
          data: [],
          loading: false,
          error: false,
        },
        traceEvidence: {
          [defaultWorkflowSpan.trace_id]: makeTraceEvidence(spans),
        },
        loading: false,
        error: false,
      },
    },
  })

  return render(
    <Provider store={store}>
      <BrowserRouter>
        <WorkflowDetailStateDiff
          defaultWorkflowSpan={defaultWorkflowSpan}
          activeStoreWorkflowSpan={defaultWorkflowSpan}
          storeDiagnosticRequest={{ data: diagnostic, loading: false, error: null }}
        />
      </BrowserRouter>
    </Provider>,
  )
}

describe('WorkflowDetailStateDiff', () => {
  it('keeps state tabs selectable when the active span has no state event', async () => {
    const user = userEvent.setup()
    const spans = loadFixtureSpans('basic_workflow_success')
    const workflowSpan = spans.find((span) => span.span_id === '1111111111111111')

    if (!workflowSpan) {
      throw new Error('Expected basic workflow span in fixture')
    }

    renderStateDiff({
      spans,
      activeSpan: workflowSpan,
      defaultWorkflowSpan: workflowSpan,
      diagnostic: loadBasicWorkflowProjection(),
    })

    expect(screen.getByText('Basic Information')).toBeInTheDocument()
    expect(screen.queryByLabelText('Workflow Store diagnostics')).not.toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Before' }))

    await waitFor(() => {
      expect(screen.queryByText('Basic Information')).not.toBeInTheDocument()
    })
    expect(screen.getByText('input')).toBeInTheDocument()
  })

  it('does not expose state projections when backend replay verification failed', async () => {
    const spans = loadFixtureSpans('basic_workflow_success')
    const workflowSpan = spans.find((span) => span.span_id === '1111111111111111')
    if (!workflowSpan) throw new Error('Expected basic workflow span in fixture')

    const detail = loadBasicWorkflowProjection()
    detail.state.reconstructable = false
    detail.state.reconstruction_status = 'failed'
    detail.state.reconstruction_reason = 'patch_replay_mismatch'
    detail.integrity.status = 'partial'
    detail.integrity.diagnostics.push({
      code: 'store_reconstruction_failed',
      path: 'state',
      message: 'The Store transition chain did not reproduce the declared end state.',
    })
    renderStateDiff({
      spans,
      activeSpan: workflowSpan,
      defaultWorkflowSpan: workflowSpan,
      diagnostic: detail,
    })

    expect(await screen.findByText('State history could not be verified')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Before' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'After' })).not.toBeInTheDocument()
    expect(screen.getByText('patch_replay_mismatch')).toBeInTheDocument()
  })
})

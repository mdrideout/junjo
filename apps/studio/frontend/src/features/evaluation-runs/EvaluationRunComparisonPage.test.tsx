import { render, screen } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { Provider } from 'react-redux'
import { MemoryRouter } from 'react-router'
import { describe, expect, it } from 'vitest'
import { API_BASE, server } from '../../auth/test-utils/mock-server'
import { store } from '../../root-store/store'
import EvaluationRunComparisonPage from './EvaluationRunComparisonPage'
import { makeEvaluationRunDetailFixture } from './testing/fixtures'

describe('EvaluationRunComparisonPage', () => {
  it('shows binary results, reasons, and spans by immutable test ID', async () => {
    const baseline = makeEvaluationRunDetailFixture({
      runId: 'view-baseline',
      attemptStatuses: ['passed', 'queued'],
    })
    const candidateFixture = makeEvaluationRunDetailFixture({
      runId: 'view-candidate',
      runLabel: 'prompt candidate',
      attemptStatuses: ['passed', 'queued'],
    })
    const candidate = {
      ...candidateFixture,
      cases: candidateFixture.cases.map((item, index) =>
        index === 0
          ? {
              ...item,
              attempt: {
                ...item.attempt,
                duration_ms: 140,
                reason: 'The candidate adds a concrete local detail.',
              },
            }
          : item,
      ),
    }
    server.use(
      http.get(`${API_BASE}/api/v1/evaluation/runs/:runId`, ({ params }) => {
        if (params.runId === baseline.run.id) return HttpResponse.json(baseline)
        if (params.runId === candidate.run.id) return HttpResponse.json(candidate)
        return HttpResponse.json({ detail: 'not found' }, { status: 404 })
      }),
    )

    render(
      <Provider store={store}>
        <MemoryRouter
          initialEntries={[
            `/evaluation-runs/compare?baseline_run_id=${baseline.run.id}&candidate_run_id=${candidate.run.id}`,
          ]}
        >
          <EvaluationRunComparisonPage />
        </MemoryRouter>
      </Provider>,
    )

    expect(await screen.findByRole('heading', { name: 'Compare runs' })).toBeInTheDocument()
    expect(screen.getByText('prompt candidate')).toBeInTheDocument()
    expect(screen.getAllByText('Response place realism').length).toBeGreaterThan(0)
    expect(screen.getByText('The candidate adds a concrete local detail.')).toBeInTheDocument()
    expect(screen.getByRole('link', {
      name: 'View candidate spans',
    })).toHaveAttribute(
      'href',
      '/resolve/executable?service_namespace=&service_name=ai-chat-evaluation&executable_type=workflow&runtime_id=view-candidate-runtime-1&destination=detail',
    )
  })

  it('rejects two runs from different datasets', async () => {
    const baseline = makeEvaluationRunDetailFixture({
      runId: 'mismatch-baseline',
      datasetId: 'dataset-one',
      attemptStatuses: ['passed'],
    })
    const candidate = makeEvaluationRunDetailFixture({
      runId: 'mismatch-candidate',
      datasetId: 'dataset-two',
      attemptStatuses: ['passed'],
    })
    server.use(
      http.get(`${API_BASE}/api/v1/evaluation/runs/:runId`, ({ params }) =>
        HttpResponse.json(params.runId === baseline.run.id ? baseline : candidate)),
    )

    render(
      <Provider store={store}>
        <MemoryRouter
          initialEntries={[
            `/evaluation-runs/compare?baseline_run_id=${baseline.run.id}&candidate_run_id=${candidate.run.id}`,
          ]}
        >
          <EvaluationRunComparisonPage />
        </MemoryRouter>
      </Provider>,
    )

    expect(await screen.findByRole('heading', {
      name: 'Evaluation runs are not comparable',
    })).toBeInTheDocument()
    expect(screen.getByText('Evaluation runs must use the same locked dataset.')).toBeInTheDocument()
  })
})

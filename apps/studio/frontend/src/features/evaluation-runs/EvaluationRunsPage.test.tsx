import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { Provider } from 'react-redux'
import { createMemoryRouter, MemoryRouter, RouterProvider } from 'react-router'
import { describe, expect, it } from 'vitest'
import { API_BASE, server } from '../../auth/test-utils/mock-server'
import { store } from '../../root-store/store'
import EvaluationRunsPage from './EvaluationRunsPage'
import {
  makeEvaluationRunDetailFixture,
  makeEvaluationRunListPage,
} from './testing/fixtures'

describe('EvaluationRunsPage', () => {
  it('shows a loading state until the bounded list response arrives', async () => {
    let releaseResponse!: () => void
    const responseReady = new Promise<void>((resolve) => {
      releaseResponse = resolve
    })
    server.use(
      http.get(`${API_BASE}/api/v1/evaluation/runs`, async () => {
        await responseReady
        return HttpResponse.json(makeEvaluationRunListPage([]))
      }),
    )

    render(
      <Provider store={store}>
        <MemoryRouter initialEntries={['/evaluation-runs?dataset_id=loading-list-dataset']}>
          <EvaluationRunsPage />
        </MemoryRouter>
      </Provider>,
    )

    expect(await screen.findByText('Loading evaluation runs…')).toBeInTheDocument()
    releaseResponse()
    expect(await screen.findByText('No evaluation runs match this filter.')).toBeInTheDocument()
  })

  it('loads one cursor page, renders active and completed runs, and preserves pagination filters', async () => {
    const baseline = makeEvaluationRunDetailFixture({
      runId: 'page-baseline',
      attemptStatuses: ['passed', 'failed'],
    })
    const candidate = makeEvaluationRunDetailFixture({
      runId: 'page-candidate',
      candidateLabel: 'prompt candidate',
      attemptStatuses: ['passed', 'queued'],
    })
    let observedQuery = ''
    server.use(
      http.get(`${API_BASE}/api/v1/evaluation/runs`, ({ request }) => {
        observedQuery = new URL(request.url).search
        return HttpResponse.json(
          makeEvaluationRunListPage([baseline, candidate], 'next/cursor'),
        )
      }),
    )

    render(
      <Provider store={store}>
        <MemoryRouter
          initialEntries={[
            '/evaluation-runs?dataset_id=eval-dataset-local-places&cursor=current%2Fcursor&limit=25',
          ]}
        >
          <EvaluationRunsPage />
        </MemoryRouter>
      </Provider>,
    )

    expect(await screen.findByRole('link', { name: /baseline page-baseline/ })).toHaveAttribute(
      'href',
      '/evaluation-runs/page-baseline',
    )
    expect(screen.getByText('active')).toBeInTheDocument()
    expect(screen.getByText('completed')).toBeInTheDocument()
    expect(observedQuery).toContain('limit=25')
    expect(observedQuery).toContain('dataset_id=eval-dataset-local-places')
    expect(observedQuery).toContain('cursor=current%2Fcursor')
    expect(screen.getByRole('link', { name: 'Next page' })).toHaveAttribute(
      'href',
      '/evaluation-runs?limit=25&dataset_id=eval-dataset-local-places&cursor=next%2Fcursor',
    )
  })

  it('navigates to a comparison defined by two explicit run IDs', async () => {
    const user = userEvent.setup()
    server.use(
      http.get(`${API_BASE}/api/v1/evaluation/runs`, () =>
        HttpResponse.json(makeEvaluationRunListPage([]))),
    )
    const router = createMemoryRouter(
      [
        { path: '/evaluation-runs', element: <EvaluationRunsPage /> },
        { path: '/evaluation-runs/compare', element: <p>Comparison destination</p> },
      ],
      { initialEntries: ['/evaluation-runs'] },
    )
    render(
      <Provider store={store}>
        <RouterProvider router={router} />
      </Provider>,
    )

    await user.type(screen.getByRole('textbox', { name: 'Baseline run ID' }), 'run baseline')
    await user.type(screen.getByRole('textbox', { name: 'Candidate run ID' }), 'run/candidate')
    await user.click(screen.getByRole('button', { name: 'Compare runs' }))

    expect(await screen.findByText('Comparison destination')).toBeInTheDocument()
    expect(router.state.location.search).toBe(
      '?baseline_run_id=run+baseline&candidate_run_id=run%2Fcandidate',
    )
  })
})

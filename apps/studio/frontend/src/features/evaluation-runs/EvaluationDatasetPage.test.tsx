import { render, screen } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { Provider } from 'react-redux'
import { MemoryRouter, Route, Routes } from 'react-router'
import { describe, expect, it } from 'vitest'
import { API_BASE, server } from '../../auth/test-utils/mock-server'
import { createAppStore } from '../../root-store/store'
import EvaluationDatasetPage from './EvaluationDatasetPage'
import {
  makeEvaluationDatasetDetailFixture,
  makeEvaluationRunDetailFixture,
  makeEvaluationRunListPage,
} from './testing/fixtures'

describe('EvaluationDatasetPage', () => {
  it('shows tests, pass conditions, provenance, and run history', async () => {
    const detail = makeEvaluationRunDetailFixture({
      runId: 'dataset-history-run',
      runLabel: 'prompt revision two',
      attemptStatuses: ['passed', 'failed'],
    })
    const datasetDetail = makeEvaluationDatasetDetailFixture(detail)
    server.use(
      http.get(`${API_BASE}/api/v1/evaluation/datasets/:datasetId`, () =>
        HttpResponse.json(datasetDetail)),
      http.get(`${API_BASE}/api/v1/evaluation/runs`, () =>
        HttpResponse.json(makeEvaluationRunListPage([detail]))),
    )

    render(
      <Provider store={createAppStore()}>
        <MemoryRouter
          initialEntries={[`/evaluation-runs/datasets/${detail.dataset.id}`]}
        >
          <Routes>
            <Route
              path="/evaluation-runs/datasets/:datasetId"
              element={<EvaluationDatasetPage />}
            />
          </Routes>
        </MemoryRouter>
      </Provider>,
    )

    expect(await screen.findByRole('heading', { name: 'Local places' })).toBeInTheDocument()
    expect(screen.getAllByText('Response place realism').length).toBeGreaterThan(0)
    expect(screen.getAllByText('Mention a real place and keep the geography plausible.').length)
      .toBeGreaterThan(0)
    expect(screen.queryByText((content) => content.includes('"rubric"'))).not.toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'View source spans' })).toHaveAttribute(
      'href',
      '/resolve/executable?service_namespace=junjo.examples&service_name=ai-chat&executable_type=workflow&runtime_id=source-runtime-1&destination=detail',
    )
    expect(screen.getByRole('link', { name: 'prompt revision two' })).toHaveAttribute(
      'href',
      '/evaluation-runs/dataset-history-run',
    )
  })
})

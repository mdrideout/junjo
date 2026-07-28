import { render, screen } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { Provider } from 'react-redux'
import { MemoryRouter, Route, Routes } from 'react-router'
import { describe, expect, it } from 'vitest'
import { API_BASE, server } from '../../auth/test-utils/mock-server'
import { store } from '../../root-store/store'
import EvaluationRunDetailPage from './EvaluationRunDetailPage'
import { makeEvaluationRunDetailFixture } from './testing/fixtures'

describe('EvaluationRunDetailPage', () => {
  it('shows a loading state until run detail arrives', async () => {
    const detail = makeEvaluationRunDetailFixture({ runId: 'loading-detail-run' })
    let releaseResponse!: () => void
    const responseReady = new Promise<void>((resolve) => {
      releaseResponse = resolve
    })
    server.use(
      http.get(`${API_BASE}/api/v1/evaluation/runs/:runId`, async () => {
        await responseReady
        return HttpResponse.json(detail)
      }),
    )

    render(
      <Provider store={store}>
        <MemoryRouter initialEntries={[`/evaluation-runs/${detail.run.id}`]}>
          <Routes>
            <Route path="/evaluation-runs/:runId" element={<EvaluationRunDetailPage />} />
          </Routes>
        </MemoryRouter>
      </Provider>,
    )

    expect(await screen.findByText('Loading evaluation run…')).toBeInTheDocument()
    releaseResponse()
    expect(await screen.findByRole('heading', { name: 'baseline' })).toBeInTheDocument()
  })

  it('shows every attempt state and links exact semantic identities without hydrating evidence', async () => {
    const detail = makeEvaluationRunDetailFixture({ runId: 'detail-all-statuses' })
    server.use(
      http.get(`${API_BASE}/api/v1/evaluation/runs/:runId`, ({ params }) => {
        expect(params.runId).toBe(detail.run.id)
        return HttpResponse.json(detail)
      }),
    )

    render(
      <Provider store={store}>
        <MemoryRouter initialEntries={[`/evaluation-runs/${detail.run.id}`]}>
          <Routes>
            <Route path="/evaluation-runs/:runId" element={<EvaluationRunDetailPage />} />
          </Routes>
        </MemoryRouter>
      </Provider>,
    )

    expect(await screen.findByRole('heading', { name: 'baseline' })).toBeInTheDocument()
    expect(screen.getByText('passed')).toBeInTheDocument()
    expect(screen.getByText('failed')).toBeInTheDocument()
    expect(screen.getByText('error')).toBeInTheDocument()
    expect(screen.getByText('queued')).toBeInTheDocument()

    const subjectLink = screen.getByRole('link', {
      name: 'Open subject evidence for local-place-1',
    })
    expect(subjectLink).toHaveAttribute(
      'href',
      '/resolve/executable?service_namespace=&service_name=ai-chat-evaluation&executable_type=workflow&runtime_id=detail-all-statuses-runtime-1&destination=detail',
    )
    expect(screen.getByRole('link', {
      name: 'Open source evidence for local-place-1',
    })).toHaveAttribute(
      'href',
      '/resolve/executable?service_namespace=junjo.examples&service_name=ai-chat&executable_type=workflow&runtime_id=source-runtime-1&destination=detail',
    )
    expect(screen.getByText('No subject execution')).toBeInTheDocument()
  })
})

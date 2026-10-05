import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { MemoryRouter, Route, Routes } from 'react-router'
import { describe, expect, it } from 'vitest'
import { API_BASE, server } from '../../auth/test-utils/mock-server'
import TracesListPage from './TracesListPage'

describe('TracesListPage', () => {
  it('asks for the traces of the chosen API key', async () => {
    const requested: string[] = []
    server.use(
      http.get(`${API_BASE}/api/v1/api-keys`, () =>
        HttpResponse.json([
          { id: 'key-a', key: 'jtel_a', name: 'Production', created_at: '2026-10-04T10:00:00Z' },
          { id: 'key-b', key: 'jtel_b', name: 'Staging', created_at: '2026-10-04T11:00:00Z' },
        ]),
      ),
      http.get(`${API_BASE}/api/v1/observability/services/:serviceName/spans/root`, ({ request }) => {
        requested.push(new URL(request.url).search)
        return HttpResponse.json([])
      }),
    )

    render(
      <MemoryRouter initialEntries={['/traces/checkout']}>
        <Routes>
          <Route path="/traces/:serviceName" element={<TracesListPage />} />
        </Routes>
      </MemoryRouter>,
    )

    // The page opens on every key, with the LLM filter on.
    await waitFor(() => expect(requested).toEqual(['?has_llm=true']))
    await screen.findByRole('option', { name: 'Staging' })

    await userEvent.selectOptions(screen.getByRole('combobox'), 'Staging')
    await waitFor(() => expect(requested.at(-1)).toBe('?has_llm=true&api_key_id=key-b'))

    await userEvent.click(screen.getByRole('checkbox'))
    await waitFor(() => expect(requested.at(-1)).toBe('?api_key_id=key-b'))

    await userEvent.selectOptions(screen.getByRole('combobox'), 'All API keys')
    await waitFor(() => expect(requested.at(-1)).toBe(''))
  })
})

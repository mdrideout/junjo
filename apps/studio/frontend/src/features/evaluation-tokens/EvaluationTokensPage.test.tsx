import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { Provider } from 'react-redux'
import { MemoryRouter } from 'react-router'
import { describe, expect, it, vi } from 'vitest'
import { API_BASE, server } from '../../auth/test-utils/mock-server'
import { createAppStore } from '../../root-store/store'
import EvaluationTokensPage from './EvaluationTokensPage'

const TOKEN_READ = {
  id: 'token-1',
  name: 'Coding agent',
  prefix: 'junjo_eval_abcd1234EFGH',
  scopes: ['evaluation:read', 'evaluation:write', 'evidence:read'],
  expires_at: null,
  revoked_at: null,
  created_by_user_id: 'user-1',
  created_at: '2026-07-27T22:00:00Z',
}

function renderPage() {
  const store = createAppStore()
  return render(
    <MemoryRouter>
      <Provider store={store}>
        <EvaluationTokensPage />
      </Provider>
    </MemoryRouter>,
  )
}

describe('EvaluationTokensPage', () => {
  it('creates a scoped token and presents its secret exactly once', async () => {
    const user = userEvent.setup()
    let createdRequest: unknown
    server.use(
      http.get(`${API_BASE}/api/v1/evaluation-tokens`, () =>
        HttpResponse.json({ items: [], next_cursor: null }),
      ),
      http.post(`${API_BASE}/api/v1/evaluation-tokens`, async ({ request }) => {
        createdRequest = await request.json()
        return HttpResponse.json(
          {
            ...TOKEN_READ,
            token:
              'junjo_eval_abcd1234EFGH.abcdefghijklmnopqrstuvwxyzABCDEFGH_12345678',
          },
          { status: 201 },
        )
      }),
    )
    renderPage()

    await user.click(screen.getByRole('button', { name: 'Create token' }))
    await user.type(screen.getByRole('textbox', { name: 'Token name' }), 'Coding agent')
    await user.click(
      screen.getByRole('button', { name: 'Create token' }),
    )

    expect(
      await screen.findByText(
        'junjo_eval_abcd1234EFGH.abcdefghijklmnopqrstuvwxyzABCDEFGH_12345678',
      ),
    ).toBeInTheDocument()
    expect(createdRequest).toEqual({
      name: 'Coding agent',
      scopes: ['evaluation:read', 'evaluation:write', 'evidence:read'],
      expires_at: null,
    })

    await user.click(screen.getByRole('button', { name: 'Done' }))
    expect(
      screen.queryByText(
        'junjo_eval_abcd1234EFGH.abcdefghijklmnopqrstuvwxyzABCDEFGH_12345678',
      ),
    ).not.toBeInTheDocument()
  })

  it('lists prefixes without secrets and revokes an active token explicitly', async () => {
    const user = userEvent.setup()
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    let revokedId: string | null = null
    let listCount = 0
    server.use(
      http.get(`${API_BASE}/api/v1/evaluation-tokens`, () => {
        listCount += 1
        return HttpResponse.json({
          items: [
            {
              ...TOKEN_READ,
              revoked_at: listCount > 1 ? '2026-07-27T23:00:00Z' : null,
            },
          ],
          next_cursor: null,
        })
      }),
      http.put(
        `${API_BASE}/api/v1/evaluation-tokens/:tokenId/revoke`,
        ({ params }) => {
          revokedId = String(params.tokenId)
          return HttpResponse.json({
            ...TOKEN_READ,
            revoked_at: '2026-07-27T23:00:00Z',
          })
        },
      ),
    )
    renderPage()

    expect(
      await screen.findByText('junjo_eval_abcd1234EFGH'),
    ).toBeInTheDocument()
    expect(screen.queryByText(/one-time-secret/)).not.toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Revoke' }))

    await waitFor(() => expect(revokedId).toBe('token-1'))
    expect(await screen.findByText('Revoked')).toBeInTheDocument()
  })

  it('loads subsequent token pages with the server cursor', async () => {
    const user = userEvent.setup()
    const cursors: Array<string | null> = []
    server.use(
      http.get(`${API_BASE}/api/v1/evaluation-tokens`, ({ request }) => {
        const cursor = new URL(request.url).searchParams.get('cursor')
        cursors.push(cursor)
        if (cursor === 'next-page') {
          return HttpResponse.json({
            items: [
              {
                ...TOKEN_READ,
                id: 'token-2',
                name: 'Second coding agent',
                prefix: 'junjo_eval_wxyz5678IJKL',
              },
            ],
            next_cursor: null,
          })
        }
        return HttpResponse.json({
          items: [TOKEN_READ],
          next_cursor: 'next-page',
        })
      }),
    )
    renderPage()

    expect(await screen.findByText('Coding agent')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Load more' }))

    expect(await screen.findByText('Second coding agent')).toBeInTheDocument()
    expect(screen.getByText('Coding agent')).toBeInTheDocument()
    expect(cursors).toEqual([null, 'next-page'])
    expect(screen.queryByRole('button', { name: 'Load more' })).not.toBeInTheDocument()
  })
})

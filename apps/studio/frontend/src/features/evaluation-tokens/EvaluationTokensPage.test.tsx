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
  token:
    'jcli_0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ_-',
  scopes: ['evaluation:read', 'evaluation:write', 'evidence:read'],
  expires_at: null,
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
  it('describes developer access without redundant credential instructions', async () => {
    server.use(
      http.get(`${API_BASE}/api/v1/evaluation-tokens`, () =>
        HttpResponse.json({ items: [], next_cursor: null }),
      ),
    )
    renderPage()

    expect(
      screen.getByRole('heading', { name: 'Developer Access Tokens' }),
    ).toBeInTheDocument()
    expect(
      screen.getByText(
        'Authenticate developer environments and coding agents that interact with Junjo AI Studio through the Junjo SDK and CLI.',
      ),
    ).toBeInTheDocument()
    expect(screen.queryByText(/JUNJO_AI_STUDIO_CLI_TOKEN/)).not.toBeInTheDocument()

    const divider = screen.getByRole('separator')
    const createButton = screen.getByRole('button', { name: 'Create access token' })
    expect(divider.compareDocumentPosition(createButton) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  })

  it('creates a scoped token with a non-expiring default', async () => {
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
              'jcli_0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ_-',
          },
          { status: 201 },
        )
      }),
    )
    renderPage()

    await user.click(screen.getByRole('button', { name: 'Create access token' }))
    const expiration = screen.getByRole('combobox', { name: 'Expiration' })
    expect(expiration).toHaveValue('never')
    expect(screen.getByRole('option', { name: '30 days' })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: '90 days' })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: '1 year' })).toBeInTheDocument()
    await user.type(screen.getByRole('textbox', { name: 'Token name' }), 'Coding agent')
    await user.click(
      screen.getByRole('button', { name: 'Create access token' }),
    )

    expect(
      await screen.findByText(
        'jcli_0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ_-',
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
        'jcli_0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ_-',
      ),
    ).not.toBeInTheDocument()
  })

  it('copies and deletes a stored access token', async () => {
    const user = userEvent.setup()
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    const copy = vi.spyOn(navigator.clipboard, 'writeText').mockResolvedValue()
    let deletedId: string | null = null
    let listCount = 0
    server.use(
      http.get(`${API_BASE}/api/v1/evaluation-tokens`, () => {
        listCount += 1
        return HttpResponse.json({
          items: listCount > 1 ? [] : [TOKEN_READ],
          next_cursor: null,
        })
      }),
      http.delete(
        `${API_BASE}/api/v1/evaluation-tokens/:tokenId`,
        ({ params }) => {
          deletedId = String(params.tokenId)
          return new HttpResponse(null, { status: 204 })
        },
      ),
    )
    renderPage()

    expect(await screen.findByText('jcli_0123456...')).toBeInTheDocument()
    expect(screen.getByRole('table')).toHaveClass('w-full', 'max-w-[1024px]')
    expect(screen.getByRole('table').parentElement).toHaveClass('shrink-0')
    expect(screen.getAllByRole('columnheader').map((header) => header.textContent)).toEqual([
      'Name',
      'Scopes',
      'Expires',
      'Status',
      'Token',
      'Actions',
    ])
    await user.click(screen.getByRole('button', { name: 'Copy access token Coding agent' }))
    expect(copy).toHaveBeenCalledWith(TOKEN_READ.token)

    await user.click(screen.getByRole('button', { name: 'Delete access token Coding agent' }))

    await waitFor(() => expect(deletedId).toBe('token-1'))
    await waitFor(() => expect(screen.queryByText('Coding agent')).not.toBeInTheDocument())
  })

  it('keeps loaded access tokens visible when a deletion fails', async () => {
    const user = userEvent.setup()
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    server.use(
      http.get(`${API_BASE}/api/v1/evaluation-tokens`, () =>
        HttpResponse.json({ items: [TOKEN_READ], next_cursor: null }),
      ),
      http.delete(`${API_BASE}/api/v1/evaluation-tokens/:tokenId`, () =>
        HttpResponse.json({}, { status: 500 }),
      ),
    )
    renderPage()

    expect(await screen.findByText('Coding agent')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Delete access token Coding agent' }))

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Failed to delete access token (500)',
    )
    expect(screen.getByText('Coding agent')).toBeInTheDocument()
    expect(screen.getByRole('table')).toBeInTheDocument()
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
                token:
                  'jcli_9876543210ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz_-',
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

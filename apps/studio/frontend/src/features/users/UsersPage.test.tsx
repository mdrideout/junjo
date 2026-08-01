import { render, screen } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { Provider } from 'react-redux'
import { describe, expect, it } from 'vitest'
import { API_BASE, server } from '../../auth/test-utils/mock-server'
import { createAppStore } from '../../root-store/store'
import UsersPage from './UsersPage'

describe('UsersPage', () => {
  it('uses the shared administration page and table layout', async () => {
    server.use(
      http.get(`${API_BASE}/users`, () =>
        HttpResponse.json([
          {
            id: 'user-1',
            email: 'owner@example.com',
            is_active: true,
            created_at: '2026-08-01T15:00:00Z',
            updated_at: '2026-08-01T15:00:00Z',
          },
        ]),
      ),
    )

    render(
      <Provider store={createAppStore()}>
        <UsersPage />
      </Provider>,
    )

    expect(await screen.findByRole('heading', { name: 'Users' })).toBeInTheDocument()
    expect(screen.getByText('Create and manage user accounts.')).toBeInTheDocument()
    const divider = screen.getByRole('separator')
    const createButton = screen.getByRole('button', { name: 'Create User' })
    expect(divider.compareDocumentPosition(createButton) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()

    const table = await screen.findByRole('table')
    expect(table).toHaveClass('w-full', 'max-w-[1024px]')
    expect(table.parentElement).toHaveClass('shrink-0')
    expect(screen.getAllByRole('columnheader').map((header) => header.textContent)).toEqual([
      'ID',
      'Email',
      'Created',
      'Actions',
    ])
    expect(screen.getByRole('button', { name: 'Delete user owner@example.com' })).toBeInTheDocument()
  })
})

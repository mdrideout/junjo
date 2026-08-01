import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { Provider } from 'react-redux'
import { describe, expect, it, vi } from 'vitest'
import { API_BASE, server } from '../../auth/test-utils/mock-server'
import { createAppStore } from '../../root-store/store'
import ApiKeysPage from './ApiKeysPage'

vi.mock('./components/OtelExporterGuide', () => ({
  default: () => <div>Application telemetry setup guide</div>,
}))

describe('ApiKeysPage', () => {
  it('uses concise application telemetry copy', async () => {
    const user = userEvent.setup()
    server.use(http.get(`${API_BASE}/api_keys`, () => HttpResponse.json([])))

    render(
      <Provider store={createAppStore()}>
        <ApiKeysPage />
      </Provider>,
    )

    expect(
      await screen.findByRole('heading', { name: 'Application Telemetry API Keys' }),
    ).toBeInTheDocument()
    expect(
      screen.getByText('Authenticate telemetry sent from your application to Junjo AI Studio.'),
    ).toBeInTheDocument()
    expect(screen.queryByText(/JUNJO_AI_STUDIO_API_KEY/)).not.toBeInTheDocument()

    const divider = screen.getByRole('separator')
    const createButton = screen.getByRole('button', { name: 'Create telemetry API key' })
    expect(divider.compareDocumentPosition(createButton) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()

    await user.click(createButton)
    expect(screen.getByRole('heading', { name: 'Create telemetry API key' })).toBeInTheDocument()
    expect(
      screen.queryByText(
        'Authenticate OTLP telemetry sent from an application to Junjo AI Studio. This key cannot manage datasets, run evaluations, or query Studio data.',
      ),
    ).not.toBeInTheDocument()
  })

  it('renders credentials in the shared table layout with copy and delete actions', async () => {
    server.use(
      http.get(`${API_BASE}/api_keys`, () =>
        HttpResponse.json([
          {
            id: 'key-1',
            key: 'jtel_0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ_-',
            name: 'AI Chat',
            created_at: '2026-08-01T15:00:00Z',
          },
        ]),
      ),
    )

    render(
      <Provider store={createAppStore()}>
        <ApiKeysPage />
      </Provider>,
    )

    const table = await screen.findByRole('table')
    expect(table).toHaveClass('w-full', 'max-w-[1024px]')
    expect(table.parentElement).toHaveClass('shrink-0')
    expect(screen.getAllByRole('columnheader').map((header) => header.textContent)).toEqual([
      'Name',
      'Created',
      'Key',
      'Actions',
    ])
    expect(screen.getByRole('button', { name: 'Copy API key AI Chat' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Delete API key AI Chat' })).toBeInTheDocument()
  })

  it('shows the generated key and explicit success actions after creation', async () => {
    const user = userEvent.setup()
    const generatedKey = 'jtel_0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ_-'
    server.use(
      http.get(`${API_BASE}/api_keys`, () => HttpResponse.json([])),
      http.post(`${API_BASE}/api_keys`, () =>
        HttpResponse.json(
          {
            id: 'key-created',
            key: generatedKey,
            name: 'AI Chat',
            created_at: '2026-08-01T15:00:00Z',
          },
          { status: 201 },
        ),
      ),
    )

    render(
      <Provider store={createAppStore()}>
        <ApiKeysPage />
      </Provider>,
    )

    await user.click(
      await screen.findByRole('button', { name: 'Create telemetry API key' }),
    )
    await user.type(screen.getByRole('textbox', { name: 'Key name' }), 'AI Chat')
    await user.click(screen.getByRole('button', { name: 'Create API key' }))

    expect(await screen.findByText(generatedKey)).toBeInTheDocument()
    expect(
      screen.getByText('API key created. You can copy it again later from API Keys.'),
    ).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Copy API key' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Done' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Create API key' })).not.toBeInTheDocument()
  })
})

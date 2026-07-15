import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { Provider } from 'react-redux'
import { MemoryRouter } from 'react-router'
import { describe, expect, it } from 'vitest'
import { API_BASE, server } from '../../auth/test-utils/mock-server'
import { store } from '../../root-store/store'
import AgentExecutionsPage from './AgentExecutionsPage'
import { makeAgentExecutionDetailFixture } from './testing/fixtures'

describe('AgentExecutionsPage', () => {
  it('queries a service-scoped semantic execution list and links to detail diagnostics', async () => {
    const fixture = makeAgentExecutionDetailFixture()
    let observedScope = ''
    server.use(
      http.get(`${API_BASE}/api/v1/agent-executions`, ({ request }) => {
        const parameters = new URL(request.url).searchParams
        observedScope = `${parameters.get('service_namespace')}:${parameters.get('service_name')}`
        return HttpResponse.json([fixture.summary])
      }),
    )

    render(
      <Provider store={store}>
        <MemoryRouter initialEntries={['/agents?service_namespace=junjo.examples&service_name=page-ai-chat']}>
          <AgentExecutionsPage />
        </MemoryRouter>
      </Provider>,
    )

    const executionLink = await screen.findByRole('link', { name: /Chat Agent/ })
    expect(observedScope).toBe('junjo.examples:page-ai-chat')
    expect(executionLink).toHaveAttribute(
      'href',
      '/agents/11111111111111111111111111111111/aaaaaaaaaaaaaaaa',
    )
  })

  it('treats an empty namespace as an explicit valid scope', async () => {
    const user = userEvent.setup()
    let observedNamespace: string | null = null
    server.use(
      http.get(`${API_BASE}/api/v1/agent-executions`, ({ request }) => {
        observedNamespace = new URL(request.url).searchParams.get('service_namespace')
        return HttpResponse.json([])
      }),
    )

    render(
      <Provider store={store}>
        <MemoryRouter initialEntries={['/agents']}>
          <AgentExecutionsPage />
        </MemoryRouter>
      </Provider>,
    )

    await user.type(screen.getByRole('textbox', { name: 'Service name' }), 'empty-namespace-ai-chat')
    await user.click(screen.getByRole('button', { name: 'Query executions' }))

    expect(await screen.findByText('No Agent executions match this service scope and filter set.')).toBeInTheDocument()
    expect(observedNamespace).toBe('')
  })
})

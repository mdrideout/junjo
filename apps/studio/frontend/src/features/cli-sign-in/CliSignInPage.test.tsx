import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { createMemoryRouter, RouterProvider } from 'react-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { AuthProvider } from '../../auth/auth-context'
import { API_BASE, server } from '../../auth/test-utils/mock-server'
import AuthGuard from '../../guards/AuthGuard'
import CliSignInPage from './CliSignInPage'

const SIGN_INS = `${API_BASE}/api/v1/cli-sign-ins`

const PENDING = {
  user_code: 'WZRP-JWSQ',
  client_name: 'junjo CLI on laptop',
  scopes: ['evaluation:read', 'evidence:read'],
  expires_at: '2026-10-04T05:32:09Z',
}
const APPROVED = {
  token_id: 'example-token-id',
  token_name: 'junjo CLI on laptop',
}
const DENIED = { message: 'CLI sign-in denied' }

const UNAUTHORIZED = { code: 'unauthorized', message: 'No valid session' }
const NOT_FOUND = { code: 'not_found', message: 'CLI sign-in not found' }
const INVALID = {
  code: 'invalid_request',
  message:
    'Invalid URL: user_code must be eight letters in two groups of four, such as WDJB-MJHT',
}

const CANNOT_BE_USED =
  'It is unknown, already used, or expired. Run the command again in your terminal to get a new code.'

function renderPage(initialEntry: string) {
  const router = createMemoryRouter(
    [{ path: '/cli-sign-in', element: <CliSignInPage /> }],
    { initialEntries: [initialEntry] },
  )
  render(<RouterProvider router={router} />)
  return router
}

describe('CliSignInPage', () => {
  it('shows what the terminal asked for, with the code most prominent', async () => {
    const requests: Array<{ path: string; credentials: string }> = []
    server.use(
      http.get(`${SIGN_INS}/:userCode`, ({ request }) => {
        requests.push({
          path: new URL(request.url).pathname,
          credentials: request.credentials,
        })
        return HttpResponse.json(PENDING)
      }),
    )
    renderPage('/cli-sign-in?code=WZRP-JWSQ')

    expect(screen.getByRole('heading', { name: 'CLI sign-in' })).toBeInTheDocument()
    expect(screen.getByText('Loading sign-in request…')).toBeInTheDocument()

    const code = await screen.findByText('WZRP-JWSQ')
    expect(code).toHaveClass('font-mono', 'text-4xl')
    expect(
      screen.getByRole('region', { name: 'Compare this code with your terminal' }),
    ).toContainElement(code)
    expect(
      screen.getByText('Your own terminal must be showing this exact code.'),
    ).toBeInTheDocument()

    const reported = within(screen.getByText('Reported by the terminal as').parentElement!)
    expect(reported.getByText('junjo CLI on laptop')).toBeInTheDocument()
    expect(
      reported.getByText('The terminal chose this name. Junjo AI Studio has not verified it.'),
    ).toBeInTheDocument()

    const requested = within(screen.getByText('Requested scopes').parentElement!)
    expect(requested.getAllByRole('listitem').map((item) => item.textContent)).toEqual([
      'Evaluation read' + 'List datasets, runs, attempts, and execution membership.',
      'Evidence read' + 'Resolve executions and retrieve their received trace evidence.',
    ])
    expect(screen.queryByText('Evaluation write')).not.toBeInTheDocument()

    const expiry = within(screen.getByText('Request expires').parentElement!)
    expect(
      expiry.getByText(new Date('2026-10-04T05:32:09Z').toLocaleString()),
    ).toBeInTheDocument()

    expect(
      screen.getByText(
        'Approving gives that terminal access to Junjo AI Studio as you, with the scopes listed above.',
      ),
    ).toBeInTheDocument()
    expect(
      screen.getByText(
        'If you did not just see this code in your own terminal, deny this request.',
      ),
    ).toBeInTheDocument()

    expect(screen.getByRole('button', { name: 'Approve' })).toBeEnabled()
    expect(screen.getByRole('button', { name: 'Deny' })).toBeEnabled()
    expect(requests).toEqual([
      { path: '/api/v1/cli-sign-ins/WZRP-JWSQ', credentials: 'include' },
    ])
  })

  it('shows the client name as plain text', async () => {
    const clientName = '<b>Verified by Junjo AI Studio</b>\nApprove this request'
    server.use(
      http.get(`${SIGN_INS}/:userCode`, () =>
        HttpResponse.json({ ...PENDING, client_name: clientName }),
      ),
    )
    renderPage('/cli-sign-in?code=WZRP-JWSQ')

    const name = (await screen.findByText('Reported by the terminal as')).nextElementSibling!
    expect(name.textContent).toBe(clientName)
    expect(name.childElementCount).toBe(0)
  })

  it('asks for the code as the link gave it and decides on the code Studio shows', async () => {
    const user = userEvent.setup()
    const requestedPaths: string[] = []
    server.use(
      http.get(`${SIGN_INS}/:userCode`, ({ request }) => {
        requestedPaths.push(new URL(request.url).pathname)
        return HttpResponse.json(PENDING)
      }),
      http.post(`${SIGN_INS}/:userCode/deny`, ({ request }) => {
        requestedPaths.push(new URL(request.url).pathname)
        return HttpResponse.json(DENIED)
      }),
    )
    renderPage('/cli-sign-in?code=%20wzrpjwsq%20')

    expect(await screen.findByText('WZRP-JWSQ')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Deny' }))
    await screen.findByRole('status')

    expect(requestedPaths).toEqual([
      '/api/v1/cli-sign-ins/wzrpjwsq',
      '/api/v1/cli-sign-ins/WZRP-JWSQ/deny',
    ])
  })

  it('approves the request, names the minted token, and links to where it is revoked', async () => {
    const user = userEvent.setup()
    const approvals: Array<{ path: string; credentials: string; body: string }> = []
    server.use(
      http.get(`${SIGN_INS}/:userCode`, () => HttpResponse.json(PENDING)),
      http.post(`${SIGN_INS}/:userCode/approve`, async ({ request }) => {
        approvals.push({
          path: new URL(request.url).pathname,
          credentials: request.credentials,
          body: await request.text(),
        })
        // Studio names the token after the client. A different name here shows
        // that the page names the token Studio minted.
        return HttpResponse.json({ ...APPROVED, token_name: 'Token minted by Studio' })
      }),
    )
    renderPage('/cli-sign-in?code=WZRP-JWSQ')

    await user.click(await screen.findByRole('button', { name: 'Approve' }))

    const outcome = await screen.findByRole('status')
    expect(within(outcome).getByRole('heading', { name: 'Sign-in approved' })).toBeInTheDocument()
    expect(outcome).toHaveTextContent(
      'The terminal will finish signing in by itself with a new developer access token named:',
    )
    expect(within(outcome).getByText('Token minted by Studio')).toBeInTheDocument()
    expect(outcome).toHaveTextContent(
      'You can revoke this token on the Developer Access Tokens page.',
    )
    expect(
      within(outcome).getByRole('link', { name: 'Developer Access Tokens' }),
    ).toHaveAttribute('href', '/access-tokens')

    expect(screen.queryByText('WZRP-JWSQ')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Approve' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Deny' })).not.toBeInTheDocument()
    expect(approvals).toEqual([
      { path: '/api/v1/cli-sign-ins/WZRP-JWSQ/approve', credentials: 'include', body: '' },
    ])
  })

  it('denies the request and says so', async () => {
    const user = userEvent.setup()
    const denials: Array<{ path: string; credentials: string; body: string }> = []
    server.use(
      http.get(`${SIGN_INS}/:userCode`, () => HttpResponse.json(PENDING)),
      http.post(`${SIGN_INS}/:userCode/deny`, async ({ request }) => {
        denials.push({
          path: new URL(request.url).pathname,
          credentials: request.credentials,
          body: await request.text(),
        })
        return HttpResponse.json(DENIED)
      }),
    )
    renderPage('/cli-sign-in?code=WZRP-JWSQ')

    await user.click(await screen.findByRole('button', { name: 'Deny' }))

    const outcome = await screen.findByRole('status')
    expect(within(outcome).getByRole('heading', { name: 'Sign-in denied' })).toBeInTheDocument()
    expect(outcome).toHaveTextContent('The terminal was not given access to Junjo AI Studio.')

    expect(screen.queryByText('WZRP-JWSQ')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Approve' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Deny' })).not.toBeInTheDocument()
    expect(denials).toEqual([
      { path: '/api/v1/cli-sign-ins/WZRP-JWSQ/deny', credentials: 'include', body: '' },
    ])
  })

  it.each([
    { first: 'Approve', outcome: 'Sign-in approved', sent: ['approve'] },
    { first: 'Deny', outcome: 'Sign-in denied', sent: ['deny'] },
  ])(
    'allows neither action again while $first is in flight',
    async ({ first, outcome, sent }) => {
      const user = userEvent.setup()
      const decisions: string[] = []
      let answer!: () => void
      const answered = new Promise<void>((resolve) => {
        answer = resolve
      })
      server.use(
        http.get(`${SIGN_INS}/:userCode`, () => HttpResponse.json(PENDING)),
        http.post(`${SIGN_INS}/:userCode/approve`, async () => {
          decisions.push('approve')
          await answered
          return HttpResponse.json(APPROVED)
        }),
        http.post(`${SIGN_INS}/:userCode/deny`, async () => {
          decisions.push('deny')
          await answered
          return HttpResponse.json(DENIED)
        }),
      )
      renderPage('/cli-sign-in?code=WZRP-JWSQ')

      await user.click(await screen.findByRole('button', { name: first }))

      const approve = screen.getByRole('button', { name: 'Approve' })
      const deny = screen.getByRole('button', { name: 'Deny' })
      expect(approve).toBeDisabled()
      expect(deny).toBeDisabled()
      await user.click(approve)
      await user.click(deny)

      answer()
      expect(await screen.findByRole('status')).toHaveTextContent(outcome)
      expect(decisions).toEqual(sent)
    },
  )

  describe('without a code', () => {
    it.each(['/cli-sign-in', '/cli-sign-in?code=', '/cli-sign-in?code=%20'])(
      'shows one field for the code at %s and asks Studio nothing',
      (initialEntry) => {
        const fetchSpy = vi.spyOn(globalThis, 'fetch')
        renderPage(initialEntry)

        expect(screen.getAllByRole('textbox')).toEqual([
          screen.getByRole('textbox', { name: 'Code shown in your terminal' }),
        ])
        expect(screen.getByRole('button', { name: 'Continue' })).toBeInTheDocument()
        expect(screen.queryByRole('button', { name: 'Approve' })).not.toBeInTheDocument()
        expect(fetchSpy).not.toHaveBeenCalled()
        fetchSpy.mockRestore()
      },
    )

    it('loads the request for the code that is submitted', async () => {
      const user = userEvent.setup()
      const requestedPaths: string[] = []
      server.use(
        http.get(`${SIGN_INS}/:userCode`, ({ request }) => {
          requestedPaths.push(new URL(request.url).pathname)
          return HttpResponse.json(PENDING)
        }),
      )
      const router = renderPage('/cli-sign-in')

      await user.type(
        screen.getByRole('textbox', { name: 'Code shown in your terminal' }),
        ' wzrp-jwsq ',
      )
      await user.click(screen.getByRole('button', { name: 'Continue' }))

      expect(await screen.findByText('WZRP-JWSQ')).toBeInTheDocument()
      expect(screen.getByRole('button', { name: 'Approve' })).toBeEnabled()
      expect(screen.queryByRole('textbox')).not.toBeInTheDocument()
      expect(requestedPaths).toEqual(['/api/v1/cli-sign-ins/wzrp-jwsq'])
      expect(router.state.location.pathname).toBe('/cli-sign-in')
      expect(new URLSearchParams(router.state.location.search).get('code')?.trim()).toBe(
        'wzrp-jwsq',
      )
    })
  })

  describe('failures', () => {
    it.each([
      { status: 404, body: NOT_FOUND },
      { status: 422, body: INVALID },
    ])('says the code cannot be used when loading answers $status', async ({ status, body }) => {
      server.use(
        http.get(`${SIGN_INS}/:userCode`, () => HttpResponse.json(body, { status })),
      )
      renderPage('/cli-sign-in?code=WZRP-JWSQ')

      const alert = await screen.findByRole('alert')
      expect(
        within(alert).getByRole('heading', { name: 'This code cannot be used' }),
      ).toBeInTheDocument()
      expect(alert).toHaveTextContent(CANNOT_BE_USED)
      expect(screen.queryByText(body.message)).not.toBeInTheDocument()
      expect(screen.queryByRole('button', { name: 'Approve' })).not.toBeInTheDocument()
      expect(screen.queryByRole('button', { name: 'Deny' })).not.toBeInTheDocument()
    })

    it('sends a typed code as one path segment, whatever it contains', async () => {
      const requestedPaths: string[] = []
      server.use(
        http.get(`${SIGN_INS}/:userCode`, ({ request }) => {
          requestedPaths.push(new URL(request.url).pathname)
          return HttpResponse.json(INVALID, { status: 422 })
        }),
      )
      renderPage(`/cli-sign-in?code=${encodeURIComponent('token/approve?x=1#y')}`)

      expect(await screen.findByRole('alert')).toHaveTextContent(CANNOT_BE_USED)
      expect(requestedPaths).toEqual([
        `/api/v1/cli-sign-ins/${encodeURIComponent('token/approve?x=1#y')}`,
      ])
    })

    it('shows the server message when loading fails another way', async () => {
      server.use(
        http.get(`${SIGN_INS}/:userCode`, () =>
          HttpResponse.json(UNAUTHORIZED, { status: 401 }),
        ),
      )
      renderPage('/cli-sign-in?code=WZRP-JWSQ')

      expect(await screen.findByRole('alert')).toHaveTextContent('No valid session')
      expect(screen.queryByText('This code cannot be used')).not.toBeInTheDocument()
      expect(screen.queryByRole('button', { name: 'Approve' })).not.toBeInTheDocument()
    })

    it('shows a status fallback when a failure carries no message', async () => {
      server.use(
        http.get(
          `${SIGN_INS}/:userCode`,
          () => new HttpResponse('Internal Server Error', { status: 500 }),
        ),
      )
      renderPage('/cli-sign-in?code=WZRP-JWSQ')

      expect(await screen.findByRole('alert')).toHaveTextContent(
        'Failed to load CLI sign-in (500)',
      )
    })

    it('says so when Studio cannot be reached', async () => {
      server.use(http.get(`${SIGN_INS}/:userCode`, () => HttpResponse.error()))
      renderPage('/cli-sign-in?code=WZRP-JWSQ')

      expect(await screen.findByRole('alert')).toHaveTextContent(
        'Unable to reach Junjo AI Studio.',
      )
    })

    it.each([
      { action: 'Approve', route: 'approve', status: 404, body: NOT_FOUND },
      { action: 'Approve', route: 'approve', status: 422, body: INVALID },
      { action: 'Deny', route: 'deny', status: 404, body: NOT_FOUND },
      { action: 'Deny', route: 'deny', status: 422, body: INVALID },
    ])(
      'says the code cannot be used when $action answers $status',
      async ({ action, route, status, body }) => {
        const user = userEvent.setup()
        server.use(
          http.get(`${SIGN_INS}/:userCode`, () => HttpResponse.json(PENDING)),
          http.post(`${SIGN_INS}/:userCode/${route}`, () =>
            HttpResponse.json(body, { status }),
          ),
        )
        renderPage('/cli-sign-in?code=WZRP-JWSQ')

        await user.click(await screen.findByRole('button', { name: action }))

        const alert = await screen.findByRole('alert')
        expect(
          within(alert).getByRole('heading', { name: 'This code cannot be used' }),
        ).toBeInTheDocument()
        expect(alert).toHaveTextContent(CANNOT_BE_USED)
        expect(screen.queryByRole('status')).not.toBeInTheDocument()
        expect(screen.queryByText('WZRP-JWSQ')).not.toBeInTheDocument()
        expect(screen.queryByRole('button', { name: 'Approve' })).not.toBeInTheDocument()
        expect(screen.queryByRole('button', { name: 'Deny' })).not.toBeInTheDocument()
      },
    )

    it.each([
      { action: 'Approve', route: 'approve', answer: APPROVED, outcome: 'Sign-in approved' },
      { action: 'Deny', route: 'deny', answer: DENIED, outcome: 'Sign-in denied' },
    ])(
      'shows the server message when $action fails another way and lets the person decide again',
      async ({ action, route, answer, outcome }) => {
        const user = userEvent.setup()
        let attempts = 0
        server.use(
          http.get(`${SIGN_INS}/:userCode`, () => HttpResponse.json(PENDING)),
          http.post(`${SIGN_INS}/:userCode/${route}`, () => {
            attempts += 1
            return attempts === 1
              ? HttpResponse.json(UNAUTHORIZED, { status: 401 })
              : HttpResponse.json(answer)
          }),
        )
        renderPage('/cli-sign-in?code=WZRP-JWSQ')

        await user.click(await screen.findByRole('button', { name: action }))

        expect(await screen.findByRole('alert')).toHaveTextContent('No valid session')
        expect(screen.getByText('WZRP-JWSQ')).toBeInTheDocument()
        expect(screen.queryByRole('status')).not.toBeInTheDocument()
        expect(screen.getByRole('button', { name: 'Approve' })).toBeEnabled()
        expect(screen.getByRole('button', { name: 'Deny' })).toBeEnabled()

        await user.click(screen.getByRole('button', { name: action }))

        expect(await screen.findByRole('status')).toHaveTextContent(outcome)
        expect(screen.queryByRole('alert')).not.toBeInTheDocument()
        expect(attempts).toBe(2)
      },
    )

    it.each([
      { action: 'Approve', route: 'approve', fallback: 'Failed to approve CLI sign-in (500)' },
      { action: 'Deny', route: 'deny', fallback: 'Failed to deny CLI sign-in (500)' },
    ])(
      'shows a status fallback when $action fails without a message',
      async ({ action, route, fallback }) => {
        const user = userEvent.setup()
        server.use(
          http.get(`${SIGN_INS}/:userCode`, () => HttpResponse.json(PENDING)),
          http.post(
            `${SIGN_INS}/:userCode/${route}`,
            () => new HttpResponse('Internal Server Error', { status: 500 }),
          ),
        )
        renderPage('/cli-sign-in?code=WZRP-JWSQ')

        await user.click(await screen.findByRole('button', { name: action }))

        expect(await screen.findByRole('alert')).toHaveTextContent(fallback)
        expect(screen.getByText('WZRP-JWSQ')).toBeInTheDocument()
      },
    )
  })
})

describe('CliSignInPage behind the sign-in guard', () => {
  beforeEach(() => {
    vi.spyOn(console, 'log').mockImplementation(() => {})
  })

  it('returns a signed-out visitor to the approval page with the code intact', async () => {
    const user = userEvent.setup()
    let signedIn = false
    const requestedPaths: string[] = []
    server.use(
      http.get(`${API_BASE}/api/v1/auth-test`, () =>
        signedIn
          ? HttpResponse.json({ user_email: 'test@example.com' })
          : HttpResponse.json(UNAUTHORIZED, { status: 401 }),
      ),
      http.post(`${API_BASE}/api/v1/sign-in`, () => {
        signedIn = true
        return HttpResponse.json({ message: 'signed in' })
      }),
      http.get(`${SIGN_INS}/:userCode`, ({ request }) => {
        requestedPaths.push(new URL(request.url).pathname)
        return HttpResponse.json({ ...PENDING, user_code: 'WDJB-MJHT' })
      }),
    )
    // The route element is the one `main.tsx` registers for this path.
    const router = createMemoryRouter(
      [
        {
          path: '/cli-sign-in',
          element: (
            <AuthGuard>
              <CliSignInPage />
            </AuthGuard>
          ),
        },
        { path: '/', element: <p>Dashboard</p> },
        { path: '/api-keys', element: <p>API keys</p> },
      ],
      { initialEntries: ['/cli-sign-in?code=WDJB-MJHT'] },
    )
    render(
      <AuthProvider>
        <RouterProvider router={router} />
      </AuthProvider>,
    )

    await user.type(await screen.findByPlaceholderText('Email address'), 'test@example.com')
    await user.type(screen.getByPlaceholderText('Password'), 'password123')
    expect(screen.queryByText('WDJB-MJHT')).not.toBeInTheDocument()
    expect(requestedPaths).toEqual([])

    await user.click(screen.getByRole('button', { name: 'Sign In' }))

    expect(await screen.findByText('WDJB-MJHT')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Approve' })).toBeEnabled()
    expect(screen.getByRole('button', { name: 'Deny' })).toBeEnabled()
    expect(screen.queryByPlaceholderText('Email address')).not.toBeInTheDocument()
    expect(requestedPaths).toEqual(['/api/v1/cli-sign-ins/WDJB-MJHT'])
    expect(router.state.location.pathname).toBe('/cli-sign-in')
    expect(router.state.location.search).toBe('?code=WDJB-MJHT')
  })
})

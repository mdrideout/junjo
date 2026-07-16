import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router'
import { describe, expect, it } from 'vitest'
import { AppShell } from './app-shell'

function renderShell(isAuthenticated: boolean, initialRoute = '/') {
  return render(
    <MemoryRouter initialEntries={[initialRoute]}>
      <AppShell isAuthenticated={isAuthenticated}>
        <p>Current page</p>
      </AppShell>
    </MemoryRouter>,
  )
}

describe('AppShell', () => {
  it('places intrinsically sized desktop navigation next to the main content', () => {
    renderShell(true)

    const desktopNavigation = screen.getByRole('complementary')
    const main = screen.getByRole('main')

    expect(desktopNavigation).toHaveClass('p-3', 'pr-6', 'shrink-0')
    expect([...desktopNavigation.classList].some((className) => className.startsWith('w-'))).toBe(false)
    expect(main).toHaveClass('min-w-0', 'flex-1')
    expect(main).not.toHaveClass('lg:pl-72')
    expect(desktopNavigation.parentElement).toHaveClass('lg:flex')
  })

  it('shows authenticated navigation and identifies the active route', () => {
    renderShell(true, '/logs/example-service')

    const desktopNavigation = screen.getByRole('complementary')
    expect(within(desktopNavigation).getByRole('link', { name: 'Logs' })).toHaveAttribute(
      'aria-current',
      'page',
    )
    expect(within(desktopNavigation).getByRole('link', { name: 'Users' })).toBeInTheDocument()
    expect(within(desktopNavigation).getByRole('link', { name: 'Agents' })).toHaveAttribute(
      'href',
      '/agents',
    )
    expect(within(desktopNavigation).queryByRole('link', { name: 'Sign in' })).not.toBeInTheDocument()
  })

  it('shows only sign-in navigation to anonymous users', () => {
    renderShell(false, '/sign-in')

    const desktopNavigation = screen.getByRole('complementary')
    expect(within(desktopNavigation).getByRole('link', { name: 'Sign in' })).toHaveAttribute(
      'aria-current',
      'page',
    )
    expect(within(desktopNavigation).queryByRole('link', { name: 'Dashboard' })).not.toBeInTheDocument()
  })

  it('opens mobile navigation, closes after routing, and returns focus', async () => {
    const user = userEvent.setup()
    renderShell(true, '/')

    const opener = screen.getByRole('button', { name: 'Open navigation' })
    await user.click(opener)

    const dialog = await screen.findByRole('dialog', { name: 'Studio navigation' })
    await user.click(within(dialog).getByRole('link', { name: 'Users' }))

    await waitFor(() => {
      expect(screen.queryByRole('dialog', { name: 'Studio navigation' })).not.toBeInTheDocument()
    })
    expect(opener).toHaveFocus()
  })

  it('closes mobile navigation with Escape', async () => {
    const user = userEvent.setup()
    renderShell(true)

    const opener = screen.getByRole('button', { name: 'Open navigation' })
    await user.click(opener)
    await screen.findByRole('dialog', { name: 'Studio navigation' })

    await user.keyboard('{Escape}')

    await waitFor(() => {
      expect(screen.queryByRole('dialog', { name: 'Studio navigation' })).not.toBeInTheDocument()
    })
    expect(opener).toHaveFocus()
  })
})

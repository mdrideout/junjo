import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { describe, expect, it } from 'vitest'
import { AppLink } from './app-link'

describe('AppLink', () => {
  it('uses client-side routes for internal destinations', () => {
    render(
      <MemoryRouter>
        <AppLink to="/settings">Settings</AppLink>
      </MemoryRouter>,
    )

    const link = screen.getByRole('link', { name: 'Settings' })
    expect(link).toHaveAttribute('href', '/settings')
    expect(link).not.toHaveAttribute('target')
  })

  it('secures external links that open a new tab', () => {
    render(
      <AppLink href="https://example.com/docs" newTab>
        Documentation
      </AppLink>,
    )

    const link = screen.getByRole('link', { name: 'Documentation' })
    expect(link).toHaveAttribute('href', 'https://example.com/docs')
    expect(link).toHaveAttribute('target', '_blank')
    expect(link).toHaveAttribute('rel', 'noopener noreferrer')
  })
})

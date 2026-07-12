/**
 * Test helper utilities for auth component integration tests.
 *
 * Provides custom render functions and utilities that wrap components
 * with necessary providers (Router, AuthContext, etc.).
 */

import { render, RenderOptions } from '@testing-library/react'
import { BrowserRouter } from 'react-router'
import { AuthProvider } from '../auth-context'
import { ReactElement, ReactNode } from 'react'

/**
 * Custom wrapper that provides all necessary context providers for auth components.
 */
function AllProviders({ children }: { children: ReactNode }) {
  return (
    <BrowserRouter>
      <AuthProvider>{children}</AuthProvider>
    </BrowserRouter>
  )
}

/**
 * Custom render function that wraps components with AuthProvider and BrowserRouter.
 *
 * Use this instead of the standard render() from @testing-library/react
 * when testing components that depend on authentication context or routing.
 *
 * @example
 * renderWithProviders(<SignInForm />)
 */
export function renderWithProviders(
  ui: ReactElement,
  options?: Omit<RenderOptions, 'wrapper'>
) {
  return render(ui, { wrapper: AllProviders, ...options })
}

// Re-export everything from React Testing Library for convenience
export * from '@testing-library/react'
export { userEvent } from '@testing-library/user-event'

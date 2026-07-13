/**
 * Test helper utilities for auth component integration tests.
 *
 * Provides custom render functions and utilities that wrap components
 * with necessary providers (Router, AuthContext, etc.).
 */

import { render, RenderOptions } from '@testing-library/react'
import type { ReactElement } from 'react'
import { AllProviders } from './test-providers'

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

export { userEvent } from '@testing-library/user-event'

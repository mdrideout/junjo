/**
 * Integration tests for SetupForm component.
 *
 * Tests the first user creation flow including:
 * - Form submission
 * - API calls (create-first-user, auth-test, db-has-users, api_keys)
 * - Navigation based on API key status
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { waitFor } from '@testing-library/react'
import { renderWithProviders, userEvent } from '../test-utils/test-helpers'
import SetupForm from './SetupForm'
import * as router from 'react-router'

// Mock useNavigate from react-router
const mockNavigate = vi.fn()
vi.mock('react-router', async () => {
  const actual = await vi.importActual('react-router')
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  }
})

describe('SetupForm', () => {
  beforeEach(() => {
    mockNavigate.mockClear()
    vi.spyOn(console, 'log').mockImplementation(() => {})
    vi.spyOn(console, 'error').mockImplementation(() => {})
  })

  it('should navigate to /api-keys after first user creation when no API keys exist', async () => {
    const user = userEvent.setup()

    // Render the SetupForm
    const { getByPlaceholderText, getByRole } = renderWithProviders(<SetupForm />)

    // Fill out the form
    const emailInput = getByPlaceholderText('Email address')
    const passwordInput = getByPlaceholderText('Password')
    const submitButton = getByRole('button', { name: /create account/i })

    await user.type(emailInput, 'newuser@example.com')
    await user.type(passwordInput, 'password123')

    // Submit the form
    await user.click(submitButton)

    // Wait for navigation to be called
    await waitFor(() => {
      expect(mockNavigate).toHaveBeenCalledWith('/api-keys')
    })
  })

  it('should display error message when user creation fails', async () => {
    const user = userEvent.setup()

    // Override the mock to return an error
    const { server } = await import('../test-utils/mock-server')
    const { http, HttpResponse } = await import('msw')

    server.use(
      http.post('http://localhost:1323/users/create-first-user', () => {
        return HttpResponse.json(
          { detail: 'User already exists' },
          { status: 409 }
        )
      }),
      // Also mock auth-test to return unauthorized (user not created, so not authenticated)
      http.get('http://localhost:1323/auth-test', () => {
        return HttpResponse.json(
          { detail: 'Unauthorized' },
          { status: 401 }
        )
      })
    )

    const { getByPlaceholderText, getByRole, findByText } = renderWithProviders(<SetupForm />)

    const emailInput = getByPlaceholderText('Email address')
    const passwordInput = getByPlaceholderText('Password')
    const submitButton = getByRole('button', { name: /create account/i })

    await user.type(emailInput, 'existing@example.com')
    await user.type(passwordInput, 'password123')
    await user.click(submitButton)

    // Should display error message
    const errorMessage = await findByText(/user already exists/i)
    expect(errorMessage).toBeInTheDocument()

    // Should NOT navigate
    expect(mockNavigate).not.toHaveBeenCalled()
  })
})

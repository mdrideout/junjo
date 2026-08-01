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
import { http, HttpResponse } from 'msw'
import { renderWithProviders, userEvent } from '../test-utils/test-helpers'
import { API_BASE, server } from '../test-utils/mock-server'
import SetupForm from './SetupForm'

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

  it('should navigate to API keys after first-user creation', async () => {
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
    server.use(
      http.post(`${API_BASE}/users/create-first-user`, () => {
        return HttpResponse.json(
          { detail: 'User already exists' },
          { status: 409 }
        )
      }),
      // Also mock auth-test to return unauthorized (user not created, so not authenticated)
      http.get(`${API_BASE}/auth-test`, () => {
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

  it('shows a status fallback when setup receives a non-JSON error', async () => {
    const user = userEvent.setup()
    server.use(
      http.post(`${API_BASE}/users/create-first-user`, () => {
        return new HttpResponse('Internal Server Error', { status: 500 })
      })
    )

    const { getByPlaceholderText, getByRole, findByText } = renderWithProviders(<SetupForm />)
    await user.type(getByPlaceholderText('Email address'), 'admin@test.com')
    await user.type(getByPlaceholderText('Password'), 'password')
    await user.click(getByRole('button', { name: /create account/i }))

    expect(await findByText('Account creation failed (500)')).toBeInTheDocument()
  })
})

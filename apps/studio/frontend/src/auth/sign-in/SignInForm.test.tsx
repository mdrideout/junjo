/**
 * Integration tests for SignInForm component.
 *
 * Tests the sign-in flow including:
 * - Form submission
 * - API calls (sign-in, api_keys)
 * - Navigation based on API key status (no keys → /api-keys, has keys → /)
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { waitFor } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { renderWithProviders, userEvent } from '../test-utils/test-helpers'
import { server } from '../test-utils/mock-server'
import SignInForm from './SignInForm'

// Mock useNavigate from react-router
const mockNavigate = vi.fn()
vi.mock('react-router', async () => {
  const actual = await vi.importActual('react-router')
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  }
})

describe('SignInForm', () => {
  beforeEach(() => {
    mockNavigate.mockClear()
    vi.spyOn(console, 'log').mockImplementation(() => {})
    vi.spyOn(console, 'error').mockImplementation(() => {})
  })

  it('should navigate to /api-keys after sign-in when user has no API keys', async () => {
    const user = userEvent.setup()

    // Default mock returns empty array for /api_keys
    const { getByPlaceholderText, getByRole } = renderWithProviders(<SignInForm />)

    const emailInput = getByPlaceholderText('Email address')
    const passwordInput = getByPlaceholderText('Password')
    const submitButton = getByRole('button', { name: /sign in/i })

    await user.type(emailInput, 'test@example.com')
    await user.type(passwordInput, 'password123')
    await user.click(submitButton)

    // Wait for navigation to be called with /api-keys
    await waitFor(() => {
      expect(mockNavigate).toHaveBeenCalledWith('/api-keys')
    })
  })

  it('should navigate to / (home) after sign-in when user has API keys', async () => {
    const user = userEvent.setup()

    // Override mock to return API keys
    server.use(
      http.get('http://localhost:1323/api_keys', () => {
        return HttpResponse.json([
          {
            id: 'existing-key-id',
            key: 'existing-key-value',
            name: 'Existing Key',
            created_at: '2025-01-01T00:00:00',
          },
        ])
      })
    )

    const { getByPlaceholderText, getByRole } = renderWithProviders(<SignInForm />)

    const emailInput = getByPlaceholderText('Email address')
    const passwordInput = getByPlaceholderText('Password')
    const submitButton = getByRole('button', { name: /sign in/i })

    await user.type(emailInput, 'test@example.com')
    await user.type(passwordInput, 'password123')
    await user.click(submitButton)

    // Wait for navigation to be called with / (home)
    await waitFor(() => {
      expect(mockNavigate).toHaveBeenCalledWith('/')
    })
  })

  it('should display error message when sign-in fails with invalid credentials', async () => {
    const user = userEvent.setup()

    // Override mock to return 401 Unauthorized
    server.use(
      http.post('http://localhost:1323/sign-in', () => {
        return HttpResponse.json(
          { detail: 'Invalid credentials' },
          { status: 401 }
        )
      }),
      // Also mock auth-test to return unauthorized (sign-in failed, user not authenticated)
      http.get('http://localhost:1323/auth-test', () => {
        return HttpResponse.json(
          { detail: 'Unauthorized' },
          { status: 401 }
        )
      })
    )

    const { getByPlaceholderText, getByRole, findByText } = renderWithProviders(<SignInForm />)

    const emailInput = getByPlaceholderText('Email address')
    const passwordInput = getByPlaceholderText('Password')
    const submitButton = getByRole('button', { name: /sign in/i })

    await user.type(emailInput, 'wrong@example.com')
    await user.type(passwordInput, 'wrongpassword')
    await user.click(submitButton)

    // Should display error message
    const errorMessage = await findByText(/invalid credentials/i)
    expect(errorMessage).toBeInTheDocument()

    // Should NOT navigate
    expect(mockNavigate).not.toHaveBeenCalled()
  })
})

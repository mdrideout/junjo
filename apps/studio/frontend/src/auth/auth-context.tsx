import { createContext, useState, ReactNode, useCallback, useEffect } from 'react'
import { UsersExistSchema } from './schema'
import { getApiHost } from '../config'

interface AuthContextType {
  isAuthenticated: boolean
  loading: boolean
  needsSetup: boolean | null
  checkAuthStatus: () => void
  checkSetupStatus: () => void
  login: (token: string) => void
  logout: () => void
}

export const AuthContext = createContext<AuthContextType>({
  isAuthenticated: false,
  loading: true,
  needsSetup: null,
  checkAuthStatus: () => {},
  checkSetupStatus: () => {},
  login: () => {},
  logout: () => {},
})

export function AuthProvider({ children }: { children: ReactNode }) {
  const [isAuthenticated, setIsAuthenticated] = useState(false)
  const [authCheckLoading, setAuthCheckLoading] = useState(true)
  const [needsSetup, setNeedsSetup] = useState<boolean | null>(null)
  const [setupCheckLoading, setSetupCheckLoading] = useState(true)

  // Combined loading state
  const loading = authCheckLoading || setupCheckLoading

  // Check if initial setup (first user creation) is needed
  const checkSetupStatus = useCallback(async () => {
    setSetupCheckLoading(true)
    try {
      // --- Use the dedicated setup status endpoint ---
      const endpoint = '/users/db-has-users'
      const response = await fetch(`${getApiHost(endpoint)}${endpoint}`, {
        method: 'GET',
      })
      if (response.ok) {
        const data = await response.json()
        const validated = UsersExistSchema.parse(data)

        const needsSetup = validated.users_exist === false
        setNeedsSetup(needsSetup)
      } else {
        // Handle errors fetching setup status (e.g., backend not ready?)
        console.error('Unexpected response from /users/db-has-users:', response.status)
        // Decide fallback: assume setup not needed? Or block? For safety, maybe assume not needed or show error.
        setNeedsSetup(false) // Fallback: Assume setup not needed on error
      }
    } catch (error) {
      console.error('Failed to check setup status:', error)
      setNeedsSetup(false) // Fallback: Assume setup not needed on error
    } finally {
      setSetupCheckLoading(false) // Finish loading for setup check
    }
  }, [])

  // Check authentication status by making a request to /auth-test
  const checkAuthStatus = useCallback(async () => {
    setAuthCheckLoading(true)
    try {
      const endpoint = '/auth-test'
      const response = await fetch(`${getApiHost(endpoint)}${endpoint}`, {
        method: 'GET',
        credentials: 'include',
      })
      if (response.ok) {
        setIsAuthenticated(true) // If the request is successful, the user is authenticated
      } else if (response.status === 401) {
        setIsAuthenticated(false) // Explicitly handle the 401
      } else {
        // Handle other errors (e.g., 500, network issues)
        console.error('Unexpected response from /auth-test:', response.status)
        setIsAuthenticated(false) // Assume not authenticated in case of other errors
      }
    } catch (error) {
      // Network errors, etc.  Assume not authenticated.
      console.error('Failed to check authentication status:', error)
      setIsAuthenticated(false)
    } finally {
      setAuthCheckLoading(false)
    }
  }, [])

  // Check authentication status on initial load
  useEffect(() => {
    checkSetupStatus()
    checkAuthStatus()
  }, [checkAuthStatus, checkSetupStatus])

  const login = () => {
    // After a successful sign-in request to your backend:
    checkAuthStatus() // Verify the session is now valid
  }

  const logout = useCallback(async () => {
    try {
      const endpoint = '/sign-out'
      const response = await fetch(`${getApiHost(endpoint)}${endpoint}`, {
        method: 'POST',
        credentials: 'include',
      })

      if (response.ok) {
        setIsAuthenticated(false)
      } else {
        console.error('Logout failed:', response.status)
        setIsAuthenticated(false) // Ensure logout even on failure (best practice)
      }
    } catch (error) {
      console.error('Logout error:', error)
      setIsAuthenticated(false) // Ensure logout even on failure (best practice)
    }
  }, [])

  return (
    <AuthContext.Provider
      value={{
        isAuthenticated,
        needsSetup,
        loading,
        checkAuthStatus,
        checkSetupStatus,
        login,
        logout,
      }}
    >
      {children}
    </AuthContext.Provider>
  )
}

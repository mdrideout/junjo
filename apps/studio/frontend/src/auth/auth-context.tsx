import { createContext, useState, ReactNode, useCallback, useEffect } from 'react'

interface AuthContextType {
  isAuthenticated: boolean
  loading: boolean
  checkAuthStatus: () => void
  login: (token: string) => void
  logout: () => void
}

export const AuthContext = createContext<AuthContextType>({
  isAuthenticated: false,
  loading: true,
  checkAuthStatus: () => {},
  login: () => {},
  logout: () => {},
})

export function AuthProvider({ children }: { children: ReactNode }) {
  const [isAuthenticated, setIsAuthenticated] = useState(false)
  const [loading, setLoading] = useState(true)

  // Check authentication status by making a request to /auth-test
  const checkAuthStatus = useCallback(async () => {
    try {
      const response = await fetch('http://localhost:1323/auth-test', {
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
      setLoading(false)
    }
  }, [])

  // Check authentication status on initial load
  useEffect(() => {
    checkAuthStatus()
  }, [checkAuthStatus])

  const login = () => {
    // After a successful sign-in request to your backend:
    checkAuthStatus() // Verify the session is now valid
  }

  const logout = useCallback(async () => {
    try {
      const response = await fetch('http://localhost:1323/sign-out', {
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
        loading,
        checkAuthStatus,
        login,
        logout,
      }}
    >
      {children}
    </AuthContext.Provider>
  )
}

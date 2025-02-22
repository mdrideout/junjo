import { createContext, useState, ReactNode, useCallback, useEffect } from 'react'
import { isTokenExpired } from './utils'

interface AuthContextType {
  isAuthenticated: boolean
  getToken: () => string | null
  login: (token: string) => void
  logout: () => void
}

export const AuthContext = createContext<AuthContextType>({
  isAuthenticated: false,
  getToken: () => null,
  login: () => {},
  logout: () => {},
})

export function AuthProvider({ children }: { children: ReactNode }) {
  const [isAuthenticated, setIsAuthenticated] = useState(false)

  const getToken = useCallback(() => {
    const token = localStorage.getItem('jwt')
    if (!token || isTokenExpired(token)) {
      localStorage.removeItem('jwt')
      setIsAuthenticated(false)
      return null
    }
    setIsAuthenticated(true)
    return token
  }, [])

  // Automatically run to set the initial isAuthenticated state
  useEffect(() => {
    getToken()
  }, [getToken])

  const login = (tokenStr: string) => {
    localStorage.setItem('jwt', tokenStr)
    setIsAuthenticated(!isTokenExpired(tokenStr))
  }

  const logout = () => {
    localStorage.removeItem('jwt')
    setIsAuthenticated(false)
  }

  return (
    <AuthContext.Provider
      value={{
        isAuthenticated,
        getToken,
        login,
        logout,
      }}
    >
      {children}
    </AuthContext.Provider>
  )
}

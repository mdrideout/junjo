import { createContext } from 'react'

export interface AuthContextType {
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

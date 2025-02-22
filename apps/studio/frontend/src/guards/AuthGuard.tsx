import { ReactNode, useContext, useEffect } from 'react'
import { useNavigate } from 'react-router'
import { AuthContext } from '../auth/auth-context'

interface AuthGuardProps {
  children: ReactNode
}

const AuthGuard = ({ children }: AuthGuardProps) => {
  const { isAuthenticated, getToken } = useContext(AuthContext)
  const navigate = useNavigate()

  useEffect(() => {
    const token = getToken()
    if (!token) {
      navigate('/sign-in')
    }
  }, [isAuthenticated, getToken, navigate])

  if (!isAuthenticated) {
    return null
  }

  return <>{children}</>
}

export default AuthGuard

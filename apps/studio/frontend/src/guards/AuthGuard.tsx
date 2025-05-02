import { ReactNode, useContext } from 'react'
import { AuthContext } from '../auth/auth-context'
import SignIn from '../auth/sign-in/SignIn'

interface AuthGuardProps {
  children: ReactNode
}

const AuthGuard = ({ children }: AuthGuardProps) => {
  const { isAuthenticated, needsSetup, loading } = useContext(AuthContext)

  if (loading) {
    return <div className="text-center">Loading...</div>
  }

  if (needsSetup === true) {
    return <div>Needs Setup</div>
  }

  if (!isAuthenticated) {
    return <SignIn />
  }

  return <>{children}</>
}

export default AuthGuard

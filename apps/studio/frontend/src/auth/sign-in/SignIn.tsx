import { useContext, useEffect } from 'react'
import SignInForm from './SignInForm'
import { AuthContext } from '../auth-context'
import SetupForm from '../setup/SetupForm'
import { useNavigate } from 'react-router'

export default function SignIn() {
  const { needsSetup, isAuthenticated, loading } = useContext(AuthContext)
  const navigate = useNavigate()

  // Redirect if already authenticated
  useEffect(() => {
    if (isAuthenticated) {
      navigate('/')
    }
  }, [isAuthenticated, navigate])

  if (loading) {
    return <div className="h-full w-full flex items-center justify-center">Loading...</div>
  }

  console.log('Sign in - needs setup? ', needsSetup)

  return (
    <div className="h-full w-full flex items-center justify-center">
      <div className="flex items-center flex-col">
        {needsSetup && <SetupForm />}
        {!needsSetup && <SignInForm />}
      </div>
    </div>
  )
}

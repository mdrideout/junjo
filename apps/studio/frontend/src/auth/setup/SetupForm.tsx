import { useContext, useEffect, useState } from 'react'
import { useNavigate } from 'react-router'
import { AuthContext } from '../auth-context'
import { getApiHost } from '../../config'
import { getPostSignInDestination } from '../navigation-helpers'

export default function SetupForm() {
  const [error, setError] = useState<string | null>(null)
  const { isAuthenticated, checkAuthStatus, checkSetupStatus } = useContext(AuthContext)
  const navigate = useNavigate()

  useEffect(() => {
    // If user is already authenticated and lands on this page, redirect to home
    // (This useEffect won't run during normal first user creation because
    // the component gets unmounted by AuthGuard when auth state changes)
    if (isAuthenticated) {
      console.log('[SetupForm] User already authenticated, redirecting to home')
      navigate('/')
    }
  }, [isAuthenticated, navigate])

  const handleSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault()

    setError(null)

    const formData = new FormData(event.currentTarget)
    const email = formData.get('email') as string
    const password = formData.get('password') as string

    // Perform setup
    try {
      const endpoint = '/users/create-first-user'
      const response = await fetch(`${getApiHost(endpoint)}${endpoint}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password }),
        credentials: 'include',
      })

      if (!response.ok) {
        const data = await response.json()

        if (data.detail) {
          throw new Error(data.detail)
        }
        if (data.message) {
          throw new Error(data.message)
        }
        throw new Error('/users/create-first-user failed')
      }

      // Check auth status to verify session was created
      // Also check setup status to update needsSetup flag
      await checkAuthStatus()
      await checkSetupStatus()

      // Navigate based on API key status
      // Must do this BEFORE AuthGuard unmounts this component
      console.log('[SetupForm] Checking API keys for navigation...')
      const destination = await getPostSignInDestination()
      console.log('[SetupForm] Navigating to:', destination)
      navigate(destination)
    } catch (err: any) {
      setError(err.message)
    }
  }

  return (
    <>
      <h1>Welcome</h1>
      <p>Create your first user account.</p>
      <div className={'h-3'} />
      <form onSubmit={handleSubmit} className="mb-6 text-black w-xs">
        <div className="flex flex-col gap-y-2">
          <input type="hidden" name="actionType" value="signIn" />
          <input
            type="email"
            name="email"
            placeholder="Email address"
            required
            className="bg-slate-300 text-black py-1 px-2 rounded-sm"
          />
          <input
            type="password"
            name="password"
            placeholder="Password"
            autoComplete="current-password"
            required
            className="bg-slate-300 text-black py-1 px-2 rounded-sm"
          />
          <button
            type="submit"
            className="py-1 px-2 bg-zinc-200 hover:bg-zinc-300 cursor-pointer rounded-md font-bold"
          >
            Create Account
          </button>
          {error && <p className="text-red-500">{error}</p>}
        </div>
      </form>
    </>
  )
}

import { useContext, useEffect, useState } from 'react'
import { useNavigate } from 'react-router'
import { AuthContext } from '../auth-context'

export default function SetupForm() {
  const [error, setError] = useState<string | null>(null)
  const { isAuthenticated } = useContext(AuthContext)
  const navigate = useNavigate()

  useEffect(() => {
    if (isAuthenticated) {
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
      const response = await fetch('http://localhost:1323/users/create-first-user', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password }),
        credentials: 'include',
      })

      if (!response.ok) {
        const data = await response.json()

        if (data.message) {
          throw new Error(data.message)
        }
        throw new Error('/users/create-first-user failed')
      }

      // Reload the page
      window.location.reload()
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

import { useContext, useEffect, useState } from 'react'
import { useNavigate } from 'react-router'
import { AuthContext } from '../auth-context'

export default function SignInForm() {
  const [error, setError] = useState<string | null>(null)
  const { isAuthenticated, login } = useContext(AuthContext)
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

    try {
      const response = await fetch('http://localhost:1323/sign-in', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password }),
      })

      if (!response.ok) {
        const data = await response.json()

        if (data.message) {
          throw new Error(data.message)
        }
        throw new Error('Sign-in failed')
      }

      const data = await response.json()
      const token = data.token
      login(token)
      navigate('/')
    } catch (err: any) {
      setError(err.message)
    }
  }

  return (
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
        <button className="py-1 px-2 bg-gray-200 hover:bg-gray-300 cursor-pointer rounded-md font-bold">Sign In</button>
        {error && <p className="text-red-500">{error}</p>}
      </div>
    </form>
  )
}

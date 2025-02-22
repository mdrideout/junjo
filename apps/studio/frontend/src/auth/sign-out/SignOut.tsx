import { useContext, useEffect } from 'react'
import { AuthContext } from '../auth-context'
import { useNavigate } from 'react-router'

export default function SignOut() {
  const { logout } = useContext(AuthContext)
  const navigate = useNavigate()

  useEffect(() => {
    logout()
    navigate('/sign-in')
  })

  return (
    <div className="h-full w-full flex items-center justify-center">
      <div className="flex items-center flex-col">
        <p>Signing out...</p>
      </div>
    </div>
  )
}

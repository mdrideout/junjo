import { useContext } from 'react'
import { Outlet } from 'react-router'
import { AuthContext } from '../auth/auth-context-value'
import { AppShell } from '../components/layout/app-shell'

export function AppLayout() {
  const { isAuthenticated } = useContext(AuthContext)

  return (
    <AppShell isAuthenticated={isAuthenticated}>
      <Outlet />
    </AppShell>
  )
}

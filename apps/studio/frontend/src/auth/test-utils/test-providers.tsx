import type { ReactNode } from 'react'
import { BrowserRouter } from 'react-router'
import { AuthProvider } from '../auth-context'

export function AllProviders({ children }: { children: ReactNode }) {
  return (
    <BrowserRouter>
      <AuthProvider>{children}</AuthProvider>
    </BrowserRouter>
  )
}

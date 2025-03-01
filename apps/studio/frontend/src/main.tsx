import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter, Route, Routes } from 'react-router'
import './index.css'
import Dashboard from './dashboard/Dashboard.tsx'
import { AppLayout } from './Layouts/AppLayout.tsx'
import SignIn from './auth/sign-in/SignIn.tsx'
import AuthGuard from './guards/AuthGuard.tsx'
import { AuthProvider } from './auth/auth-context.tsx'
import SignOut from './auth/sign-out/SignOut.tsx'
import WorkflowLogPage from './workflow-logs/log-page/WorkflowLogPage.tsx'
import WorkflowListPage from './workflow-logs/WorkflowListPage.tsx'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import ReactFlowLayout1 from './react-flow/react-flow-layout-1.tsx'

const queryClient = new QueryClient()

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <BrowserRouter>
      <QueryClientProvider client={queryClient}>
        <AuthProvider>
          <Routes>
            <Route element={<AppLayout />}>
              <Route path="/sign-in" element={<SignIn />} />
              <Route path="/sign-out" element={<SignOut />} />
              <Route
                path="/"
                element={
                  <AuthGuard>
                    <Dashboard />
                  </AuthGuard>
                }
              />
              <Route
                path="/logs"
                element={
                  <AuthGuard>
                    <WorkflowListPage />
                  </AuthGuard>
                }
              />
              <Route path="/rf-layout-1" element={<ReactFlowLayout1 />} />
              <Route path="/logs/:ExecID" element={<WorkflowLogPage />} />
            </Route>
          </Routes>
        </AuthProvider>
      </QueryClientProvider>
    </BrowserRouter>
  </StrictMode>,
)

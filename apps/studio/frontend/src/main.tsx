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
import WorkflowDetailPage from './workflow-logs/workflow-detail/WorkflowDetailPage.tsx'
import WorkflowListPage from './workflow-logs/list-workflow-executions/WorkflowListPage.tsx'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ReactFlowProvider } from '@xyflow/react'
import AppNamesPage from './workflow-logs/list-app-names/AppNamesPage.tsx'

const queryClient = new QueryClient()

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <BrowserRouter>
      <QueryClientProvider client={queryClient}>
        <ReactFlowProvider>
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
                      <AppNamesPage />
                    </AuthGuard>
                  }
                />
                <Route
                  path="/logs/:AppName"
                  element={
                    <AuthGuard>
                      <WorkflowListPage />
                    </AuthGuard>
                  }
                />
                <Route
                  path="/logs/:AppName/:ExecID"
                  element={
                    <AuthGuard>
                      <WorkflowDetailPage />
                    </AuthGuard>
                  }
                />
              </Route>
            </Routes>
          </AuthProvider>
        </ReactFlowProvider>
      </QueryClientProvider>
    </BrowserRouter>
  </StrictMode>,
)

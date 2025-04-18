import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter, Route, Routes } from 'react-router'
import './css/index.css'
import Dashboard from './features/dashboard/Dashboard.tsx'
import { AppLayout } from './Layouts/AppLayout.tsx'
import SignIn from './auth/sign-in/SignIn.tsx'
import AuthGuard from './guards/AuthGuard.tsx'
import { AuthProvider } from './auth/auth-context.tsx'
import SignOut from './auth/sign-out/SignOut.tsx'
import WorkflowDetailPage from './features/workflow-logs/workflow-detail/WorkflowDetailPage.tsx'
import WorkflowListPage from './features/workflow-logs/list-workflow-executions/WorkflowListPage.tsx'
import AppNamesPage from './features/workflow-logs/list-app-names/AppNamesPage.tsx'
import { store } from './root-store/store.ts'
import { Provider } from 'react-redux'
import { ActiveSpanProvider } from './features/workflow-logs/workflow-detail/ActiveNodeContext.tsx'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <BrowserRouter>
      <Provider store={store}>
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
                path="/logs/:serviceName"
                element={
                  <AuthGuard>
                    <WorkflowListPage />
                  </AuthGuard>
                }
              />
              <Route
                path="/logs/:serviceName/:workflowSpanID"
                element={
                  <AuthGuard>
                    <ActiveSpanProvider>
                      <WorkflowDetailPage />
                    </ActiveSpanProvider>
                  </AuthGuard>
                }
              />
            </Route>
          </Routes>
        </AuthProvider>
      </Provider>
    </BrowserRouter>
  </StrictMode>,
)

import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter, Route, Routes } from 'react-router'
import './css/index.css'
import DashboardPage from './features/dashboard/DashboardPage.tsx'
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
import { MermaidProvider } from './mermaidjs/mermaid-provider.tsx'
import UsersPage from './features/users/UsersPage.tsx'
import ApiKeysPage from './features/api-keys/ApiKeysPage.tsx'
import TracesListPage from './features/traces/TracesListPage.tsx'
import TraceDetails from './features/traces/TraceDetails.tsx'
import PromptPlaygroundPage from './features/prompt-playground/PromptPlaygroundPage.tsx'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <BrowserRouter>
      <Provider store={store}>
        <AuthProvider>
          <MermaidProvider>
            <Routes>
              <Route element={<AppLayout />}>
                <Route path="/sign-in" element={<SignIn />} />
                <Route path="/sign-out" element={<SignOut />} />
                <Route
                  path="/"
                  element={
                    <AuthGuard>
                      <DashboardPage />
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
                      <WorkflowDetailPage />
                    </AuthGuard>
                  }
                />
                <Route
                  path="/users"
                  element={
                    <AuthGuard>
                      <UsersPage />
                    </AuthGuard>
                  }
                />
                <Route
                  path="/api-keys"
                  element={
                    <AuthGuard>
                      <ApiKeysPage />
                    </AuthGuard>
                  }
                />
                <Route
                  path="/traces/:serviceName"
                  element={
                    <AuthGuard>
                      <TracesListPage />
                    </AuthGuard>
                  }
                />
                <Route
                  path="/traces/:serviceName/:traceId"
                  element={
                    <AuthGuard>
                      <TraceDetails />
                    </AuthGuard>
                  }
                />
                <Route
                  path="/traces/:serviceName/:traceId/:spanId/prompt-playground"
                  element={
                    <AuthGuard>
                      <PromptPlaygroundPage />
                    </AuthGuard>
                  }
                />
              </Route>
            </Routes>
          </MermaidProvider>
        </AuthProvider>
      </Provider>
    </BrowserRouter>
  </StrictMode>,
)

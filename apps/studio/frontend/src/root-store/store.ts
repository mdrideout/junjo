import { configureStore } from '@reduxjs/toolkit'
import workflowDetailSlice from '../features/junjo-data/workflow-detail/store/slice'
import usersSlice from '../features/users/slice'
import { usersStateListenerMiddleware } from '../features/users/listeners'
import { apiKeysReducer } from '../features/api-keys/slice'
import { apiKeysStateListenerMiddleware } from '../features/api-keys/listeners'
import { settingsReducer } from '../features/settings/slice'
import { settingsStateListenerMiddleware } from '../features/settings/listeners'
import promptPlaygroundSlice from '../features/prompt-playground/store/slice'
import workflowSpanListSlice from '../features/junjo-data/list-spans-workflow/store/slice'
import { workflowExecutionsListenerMiddleware } from '../features/junjo-data/list-spans-workflow/store/listeners'
import tracesSlice from '../features/traces/store/slice'
import { otelStateListenerMiddleware as tracesStateListenerMiddleware } from '../features/traces/store/listeners'
import { agentExecutionsReducer } from '../features/agent-executions/store/slice'
import { agentExecutionsListenerMiddleware } from '../features/agent-executions/store/listeners'
import { evaluationRunsReducer } from '../features/evaluation-runs/store/slice'
import { evaluationRunsListenerMiddleware } from '../features/evaluation-runs/store/listeners'
import { evaluationTokensReducer } from '../features/evaluation-tokens/store/slice'
import { evaluationTokensListenerMiddleware } from '../features/evaluation-tokens/store/listeners'

export function createAppStore() {
  return configureStore({
    reducer: {
      workflowDetailState: workflowDetailSlice,
      usersState: usersSlice,
      apiKeysState: apiKeysReducer,
      settingsState: settingsReducer,
      promptPlaygroundState: promptPlaygroundSlice,
      workflowSpanListState: workflowSpanListSlice,
      tracesState: tracesSlice,
      agentExecutionsState: agentExecutionsReducer,
      evaluationRunsState: evaluationRunsReducer,
      evaluationTokensState: evaluationTokensReducer,
    },

    middleware: (getDefaultMiddleware) =>
      getDefaultMiddleware()
        // Listener middleware must be prepended
        .prepend(
          usersStateListenerMiddleware.middleware,
          apiKeysStateListenerMiddleware.middleware,
          settingsStateListenerMiddleware.middleware,
          workflowExecutionsListenerMiddleware.middleware,
          tracesStateListenerMiddleware.middleware,
          agentExecutionsListenerMiddleware.middleware,
          evaluationRunsListenerMiddleware.middleware,
          evaluationTokensListenerMiddleware.middleware,
        ),
  })
}

export const store = createAppStore()
export type AppStore = ReturnType<typeof createAppStore>
export type RootState = ReturnType<AppStore['getState']>
export type AppDispatch = AppStore['dispatch']

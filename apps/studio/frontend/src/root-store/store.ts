import { configureStore } from '@reduxjs/toolkit'
import otelSlice from '../features/otel/store/slice'
import { otelStateListenerMiddleware } from '../features/otel/store/listeners'
import workflowDetailSlice from '../features/junjo-data/workflow-detail/store/slice'
import usersSlice from '../features/users/slice'
import { usersStateListenerMiddleware } from '../features/users/listeners'
import { apiKeysReducer } from '../features/api-keys/slice'
import { apiKeysStateListenerMiddleware } from '../features/api-keys/listeners'
import { workflowDetailListenerMiddleware } from '../features/junjo-data/workflow-detail/store/listeners'
import promptPlaygroundSlice from '../features/prompt-playground/store/slice'
import workflowExecutionsSlice from '../features/junjo-data/list-workflow-executions/store/slice'
import { workflowExecutionsListenerMiddleware } from '../features/junjo-data/list-workflow-executions/store/listeners'
import tracesSlice from '../features/traces/store/slice'
import { otelStateListenerMiddleware as tracesStateListenerMiddleware } from '../features/traces/store/listeners'

export const store = configureStore({
  reducer: {
    otelState: otelSlice,
    workflowDetailState: workflowDetailSlice,
    usersState: usersSlice,
    apiKeysState: apiKeysReducer,
    promptPlaygroundState: promptPlaygroundSlice,
    workflowExecutionsState: workflowExecutionsSlice,
    tracesState: tracesSlice,
  },

  middleware: (getDefaultMiddleware) =>
    getDefaultMiddleware()
      // Listener middleware must be prepended
      .prepend(
        otelStateListenerMiddleware.middleware,
        workflowDetailListenerMiddleware.middleware,
        usersStateListenerMiddleware.middleware,
        apiKeysStateListenerMiddleware.middleware,
        workflowExecutionsListenerMiddleware.middleware,
        tracesStateListenerMiddleware.middleware,
      ),
})

// Infer the `RootState` and `AppDispatch` types from the store itself
export type RootState = ReturnType<typeof store.getState>
// Inferred type: {posts: PostsState, comments: CommentsState, users: UsersState}
export type AppDispatch = typeof store.dispatch

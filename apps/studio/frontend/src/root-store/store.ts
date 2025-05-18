import { configureStore } from '@reduxjs/toolkit'
import otelSlice from '../features/otel/store/slice'
import { otelStateListenerMiddleware } from '../features/otel/store/listeners'
import workflowDetailSlice from '../features/workflow-logs/workflow-detail/store/slice'
import usersSlice from '../features/users/slice'
import { usersStateListenerMiddleware } from '../features/users/listeners'
import { apiKeysReducer } from '../features/api-keys/slice'
import { apiKeysStateListenerMiddleware } from '../features/api-keys/listeners'
import { workflowDetailListenerMiddleware } from '../features/workflow-logs/workflow-detail/store/listeners'

export const store = configureStore({
  reducer: {
    otelState: otelSlice,
    workflowDetailState: workflowDetailSlice,
    usersState: usersSlice,
    apiKeysState: apiKeysReducer,
  },

  middleware: (getDefaultMiddleware) =>
    getDefaultMiddleware()
      // Listener middleware must be prepended
      .prepend(
        otelStateListenerMiddleware.middleware,
        workflowDetailListenerMiddleware.middleware,
        usersStateListenerMiddleware.middleware,
        apiKeysStateListenerMiddleware.middleware,
      ),
})

// Infer the `RootState` and `AppDispatch` types from the store itself
export type RootState = ReturnType<typeof store.getState>
// Inferred type: {posts: PostsState, comments: CommentsState, users: UsersState}
export type AppDispatch = typeof store.dispatch

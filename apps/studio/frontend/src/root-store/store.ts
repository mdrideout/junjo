import { configureStore } from '@reduxjs/toolkit'
import workflowDetailSlice from '../features/junjo-data/workflow-detail/store/slice'
import usersSlice from '../features/users/slice'
import { usersStateListenerMiddleware } from '../features/users/listeners'
import { apiKeysReducer } from '../features/api-keys/slice'
import { apiKeysStateListenerMiddleware } from '../features/api-keys/listeners'
import { workflowDetailListenerMiddleware } from '../features/junjo-data/workflow-detail/store/listeners'
import promptPlaygroundSlice from '../features/prompt-playground/store/slice'
import workflowSpanListSlice from '../features/junjo-data/list-spans-workflow/store/slice'
import { workflowExecutionsListenerMiddleware } from '../features/junjo-data/list-spans-workflow/store/listeners'
import tracesSlice from '../features/traces/store/slice'
import { otelStateListenerMiddleware as tracesStateListenerMiddleware } from '../features/traces/store/listeners'

export const store = configureStore({
  reducer: {
    workflowDetailState: workflowDetailSlice,
    usersState: usersSlice,
    apiKeysState: apiKeysReducer,
    promptPlaygroundState: promptPlaygroundSlice,
    workflowSpanListState: workflowSpanListSlice,
    tracesState: tracesSlice,
  },

  middleware: (getDefaultMiddleware) =>
    getDefaultMiddleware()
      // Listener middleware must be prepended
      .prepend(
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

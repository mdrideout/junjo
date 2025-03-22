import { configureStore } from '@reduxjs/toolkit'
import otelSlice from '../features/otel/store/slice'
import { otelStateListenerMiddleware } from '../features/otel/store/listeners'

export const store = configureStore({
  reducer: {
    otelState: otelSlice,
  },

  middleware: (getDefaultMiddleware) =>
    getDefaultMiddleware()
      // Listener middleware must be prepended
      .prepend(otelStateListenerMiddleware.middleware),
})

// Infer the `RootState` and `AppDispatch` types from the store itself
export type RootState = ReturnType<typeof store.getState>
// Inferred type: {posts: PostsState, comments: CommentsState, users: UsersState}
export type AppDispatch = typeof store.dispatch

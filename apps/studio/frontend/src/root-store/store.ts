import { configureStore } from '@reduxjs/toolkit'
import logSlice from '../features/workflow-logs/store/slice'
// ...

export const store = configureStore({
  reducer: {
    logState: logSlice,
  },
})

// Infer the `RootState` and `AppDispatch` types from the store itself
export type RootState = ReturnType<typeof store.getState>
// Inferred type: {posts: PostsState, comments: CommentsState, users: UsersState}
export type AppDispatch = typeof store.dispatch

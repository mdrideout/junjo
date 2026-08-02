import { createSlice } from '@reduxjs/toolkit'
import type { PayloadAction } from '@reduxjs/toolkit'
import { ListUsersResponse } from './schema'

interface UsersState {
  users: ListUsersResponse
  loading: boolean
  error: string | null
  lastUpdated: number | null
}

const initialState: UsersState = {
  users: [],
  loading: false,
  error: null,
  lastUpdated: null,
}

export const usersSlice = createSlice({
  name: 'usersState',
  initialState,
  reducers: {
    fetchUsersData: {
      reducer: () => {
        // Triggers listener middleware
      },
      prepare: (payload: { force: boolean }) => ({ payload }),
    },
    deleteUser: {
      reducer: () => {
        // Triggers listener middleware
      },
      prepare: (payload: { id: string }) => ({ payload }),
    },
    loadStarted: (state) => {
      state.loading = true
      state.error = null
    },
    loadSucceeded: (state, action: PayloadAction<{ users: ListUsersResponse; fetchedAt: number }>) => {
      state.users = action.payload.users
      state.loading = false
      state.error = null
      state.lastUpdated = action.payload.fetchedAt
    },
    loadFailed: (state, action: PayloadAction<string>) => {
      state.loading = false
      state.error = action.payload
    },
    deleteStarted: (state) => {
      state.loading = true
      state.error = null
    },
    deleteSucceeded: (state) => {
      state.loading = false
      state.error = null
    },
    deleteFailed: (state, action: PayloadAction<string>) => {
      state.loading = false
      state.error = action.payload
    },
  },
})

export const UsersStateActions = usersSlice.actions
export default usersSlice.reducer

import { createSlice } from '@reduxjs/toolkit'
import type { PayloadAction } from '@reduxjs/toolkit'
import { ListUsersResponse } from './schema'

interface UsersState {
  users: ListUsersResponse
  loading: boolean
  error: boolean
  lastUpdated: number | null
}

const initialState: UsersState = {
  users: [],
  loading: false,
  error: false,
  lastUpdated: null,
}

export const usersSlice = createSlice({
  name: 'usersState',
  initialState,
  reducers: {
    fetchUsersData: (_state, _action: PayloadAction<{ force: boolean }>) => {
      // Triggers listener middleware
    },
    deleteUser: (_state, _action: PayloadAction<{ id: number }>) => {
      // Triggers listener middleware
    },
    setUsers: (state, action: PayloadAction<ListUsersResponse>) => {
      state.users = action.payload
      state.lastUpdated = Date.now()
    },
    setLoading: (state, action: PayloadAction<boolean>) => {
      state.loading = action.payload
    },
    setError: (state, action: PayloadAction<boolean>) => {
      state.error = action.payload
    },
  },
})

export const UsersStateActions = usersSlice.actions
export default usersSlice.reducer

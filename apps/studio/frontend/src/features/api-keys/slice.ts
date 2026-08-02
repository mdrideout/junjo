import { createSlice } from '@reduxjs/toolkit'
import type { PayloadAction } from '@reduxjs/toolkit'
import { ListApiKeysResponse } from './schemas'

interface ApiKeysState {
  apiKeys: ListApiKeysResponse
  loading: boolean
  error: string | null
  lastUpdated: number | null
}

const initialState: ApiKeysState = {
  apiKeys: [],
  loading: false,
  error: null,
  lastUpdated: null,
}

export const apiKeysSlice = createSlice({
  name: 'apiKeysState',
  initialState,
  reducers: {
    fetchApiKeysData: {
      reducer: () => {
        // listener triggers
      },
      prepare: (payload: { force: boolean }) => ({ payload }),
    },
    deleteApiKey: {
      reducer: () => {
        // listener triggers
      },
      prepare: (payload: { id: string }) => ({ payload }),
    },
    loadStarted: (state) => {
      state.loading = true
      state.error = null
    },
    loadSucceeded: (state, action: PayloadAction<{ apiKeys: ListApiKeysResponse; fetchedAt: number }>) => {
      state.apiKeys = action.payload.apiKeys
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

export const ApiKeysStateActions = apiKeysSlice.actions
export const apiKeysReducer = apiKeysSlice.reducer

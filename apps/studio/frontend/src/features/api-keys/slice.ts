import { createSlice } from '@reduxjs/toolkit'
import type { PayloadAction } from '@reduxjs/toolkit'
import { ListApiKeysResponse } from './schemas'

interface ApiKeysState {
  apiKeys: ListApiKeysResponse
  loading: boolean
  error: boolean
  lastUpdated: number | null
}

const initialState: ApiKeysState = {
  apiKeys: [],
  loading: false,
  error: false,
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
    setApiKeys: (state, action: PayloadAction<ListApiKeysResponse>) => {
      state.apiKeys = action.payload
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

export const ApiKeysStateActions = apiKeysSlice.actions
export const apiKeysReducer = apiKeysSlice.reducer

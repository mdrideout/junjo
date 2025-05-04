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
    fetchApiKeysData: (_state, _action: PayloadAction<{ force: boolean }>) => {
      // listener triggers
    },
    deleteApiKey: (_state, _action: PayloadAction<{ key: string }>) => {
      // listener triggers
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

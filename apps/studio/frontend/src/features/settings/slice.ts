import { createSlice } from '@reduxjs/toolkit'
import type { PayloadAction } from '@reduxjs/toolkit'

interface SettingsState {
  flushWalLoading: boolean
  flushWalError: string | null
  flushWalSuccess: boolean
  lastFlushTime: number | null
}

const initialState: SettingsState = {
  flushWalLoading: false,
  flushWalError: null,
  flushWalSuccess: false,
  lastFlushTime: null,
}

export const settingsSlice = createSlice({
  name: 'settingsState',
  initialState,
  reducers: {
    flushWal: () => {
      // listener triggers
    },
    flushWalStarted: (state) => {
      state.flushWalLoading = true
      state.flushWalError = null
      state.flushWalSuccess = false
    },
    flushWalFailed: (state, action: PayloadAction<string>) => {
      state.flushWalLoading = false
      state.flushWalError = action.payload
      state.flushWalSuccess = false
    },
    flushWalSucceeded: (state, action: PayloadAction<{ completedAt: number }>) => {
      state.flushWalLoading = false
      state.flushWalError = null
      state.flushWalSuccess = true
      state.lastFlushTime = action.payload.completedAt
    },
    resetFlushWalState: (state) => {
      state.flushWalLoading = false
      state.flushWalError = null
      state.flushWalSuccess = false
    },
  },
})

export const SettingsStateActions = settingsSlice.actions
export const settingsReducer = settingsSlice.reducer

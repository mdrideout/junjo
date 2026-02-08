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
    flushWal: (_state) => {
      // listener triggers
    },
    setFlushWalLoading: (state, action: PayloadAction<boolean>) => {
      state.flushWalLoading = action.payload
    },
    setFlushWalError: (state, action: PayloadAction<string | null>) => {
      state.flushWalError = action.payload
    },
    setFlushWalSuccess: (state, action: PayloadAction<boolean>) => {
      state.flushWalSuccess = action.payload
      if (action.payload) {
        state.lastFlushTime = Date.now()
      }
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

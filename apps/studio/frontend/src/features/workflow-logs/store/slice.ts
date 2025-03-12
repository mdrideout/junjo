import { createSlice } from '@reduxjs/toolkit'
import type { PayloadAction } from '@reduxjs/toolkit'
import { RootState } from '../../../root-store/store'

interface LogState {
  appNames: string[]
}

const initialState: LogState = {
  appNames: [],
}

export const logSlice = createSlice({
  name: 'logState',
  initialState,
  reducers: {
    setAppNames: (state, action: PayloadAction<string[]>) => {
      state.appNames = action.payload
    },
  },
})

export const LogStateActions = logSlice.actions

// Selectors
export const selectAppNames = (state: RootState) => state.logState.appNames

// Reducer
export default logSlice.reducer

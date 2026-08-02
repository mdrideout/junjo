import { createSlice, type PayloadAction } from '@reduxjs/toolkit'
import type { EvaluationTokenRead } from '../schemas'

interface EvaluationTokensState {
  items: EvaluationTokenRead[]
  loading: boolean
  error: string | null
  lastUpdated: number | null
  nextCursor: string | null
}

const initialState: EvaluationTokensState = {
  items: [],
  loading: false,
  error: null,
  lastUpdated: null,
  nextCursor: null,
}

export const evaluationTokensSlice = createSlice({
  name: 'evaluationTokensState',
  initialState,
  reducers: {
    fetchTokens: {
      reducer: () => undefined,
      prepare: (payload: { force: boolean; cursor?: string }) => ({ payload }),
    },
    deleteToken: {
      reducer: () => undefined,
      prepare: (payload: { id: string }) => ({ payload }),
    },
    loadStarted: (state) => {
      state.loading = true
      state.error = null
    },
    loadSucceeded: (
      state,
      action: PayloadAction<{
        items: EvaluationTokenRead[]
        nextCursor: string | null
        append: boolean
        fetchedAt: number
      }>,
    ) => {
      if (action.payload.append) {
        const knownIds = new Set(state.items.map((item) => item.id))
        state.items.push(...action.payload.items.filter((item) => !knownIds.has(item.id)))
      } else {
        state.items = action.payload.items
      }
      state.nextCursor = action.payload.nextCursor
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

export const EvaluationTokensActions = evaluationTokensSlice.actions
export const evaluationTokensReducer = evaluationTokensSlice.reducer

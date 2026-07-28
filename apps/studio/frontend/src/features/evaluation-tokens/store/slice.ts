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
    revokeToken: {
      reducer: () => undefined,
      prepare: (payload: { id: string }) => ({ payload }),
    },
    setTokens: (
      state,
      action: PayloadAction<{
        items: EvaluationTokenRead[]
        nextCursor: string | null
        append: boolean
      }>,
    ) => {
      if (action.payload.append) {
        const knownIds = new Set(state.items.map((item) => item.id))
        state.items.push(
          ...action.payload.items.filter((item) => !knownIds.has(item.id)),
        )
      } else {
        state.items = action.payload.items
      }
      state.nextCursor = action.payload.nextCursor
      state.lastUpdated = Date.now()
    },
    setLoading: (state, action: PayloadAction<boolean>) => {
      state.loading = action.payload
    },
    setError: (state, action: PayloadAction<string | null>) => {
      state.error = action.payload
    },
  },
})

export const EvaluationTokensActions = evaluationTokensSlice.actions
export const evaluationTokensReducer = evaluationTokensSlice.reducer

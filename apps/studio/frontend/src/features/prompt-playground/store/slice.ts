import { createSlice } from '@reduxjs/toolkit'
import type { PayloadAction } from '@reduxjs/toolkit'

export interface GenerationSettings {
  // OpenAI
  reasoning_effort?: 'minimal' | 'low' | 'medium' | 'high'
  max_completion_tokens?: number

  // Anthropic
  thinking_enabled?: boolean
  thinking_budget_tokens?: number

  // Shared
  temperature?: number
  max_tokens?: number

  // Gemini
  thinkingBudget?: number
  includeThoughts?: boolean
  maxOutputTokens?: number
}

interface PromptPlaygroundState {
  output: string | null
  loading: boolean
  error: string | null
  selectedModel: string | null
  selectedProvider: string | null
  jsonMode: boolean
  generationSettings: GenerationSettings
}

const initialState: PromptPlaygroundState = {
  output: null,
  loading: false,
  error: null,
  selectedModel: null,
  selectedProvider: null,
  jsonMode: false,
  generationSettings: {},
}

export const promptPlaygroundSlice = createSlice({
  name: 'promptPlayground',
  initialState,
  reducers: {
    setOutput: (state, action: PayloadAction<string | null>) => {
      state.output = action.payload
    },
    setLoading: (state, action: PayloadAction<boolean>) => {
      state.loading = action.payload
    },
    setError: (state, action: PayloadAction<string | null>) => {
      state.error = action.payload
    },
    setSelectedModel: (state, action: PayloadAction<string | null>) => {
      state.selectedModel = action.payload
    },
    setSelectedProvider: (state, action: PayloadAction<string | null>) => {
      state.selectedProvider = action.payload
    },
    setJsonMode: (state, action: PayloadAction<boolean>) => {
      state.jsonMode = action.payload
    },
    setGenerationSettings: (state, action: PayloadAction<GenerationSettings>) => {
      state.generationSettings = action.payload
    },
    updateGenerationSetting: <K extends keyof GenerationSettings>(
      state: PromptPlaygroundState,
      action: PayloadAction<{ key: K; value: GenerationSettings[K] }>
    ) => {
      state.generationSettings[action.payload.key] = action.payload.value
    },
    resetGenerationSettings: (state) => {
      state.generationSettings = {}
    },
  },
})

export const PromptPlaygroundActions = promptPlaygroundSlice.actions
export default promptPlaygroundSlice.reducer

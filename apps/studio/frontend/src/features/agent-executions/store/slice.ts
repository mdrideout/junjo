import { createSlice, type PayloadAction } from '@reduxjs/toolkit'
import type { AgentExecutionDetail, AgentExecutionSummary } from '../schemas/agent-execution'
import type { AgentExecutionQuery } from '../schemas/query'

export interface AgentExecutionListRequestState {
  data: AgentExecutionSummary[]
  loading: boolean
  error: string | null
}

export interface AgentExecutionDetailRequestState {
  data: AgentExecutionDetail | null
  loading: boolean
  error: string | null
}

export interface AgentExecutionsState {
  lists: Record<string, AgentExecutionListRequestState>
}

export const initialAgentExecutionsState: AgentExecutionsState = {
  lists: {},
}

function listRequestState(state: AgentExecutionsState, key: string): AgentExecutionListRequestState {
  state.lists[key] ??= { data: [], loading: false, error: null }
  return state.lists[key]
}

export const agentExecutionsSlice = createSlice({
  name: 'agentExecutionsState',
  initialState: initialAgentExecutionsState,
  reducers: {
    fetchAgentExecutions: {
      reducer: () => {
        // Listener middleware owns the request.
      },
      prepare: (query: AgentExecutionQuery) => ({ payload: query }),
    },
    setListLoading: (state, action: PayloadAction<{ key: string; loading: boolean }>) => {
      listRequestState(state, action.payload.key).loading = action.payload.loading
    },
    setListError: (state, action: PayloadAction<{ key: string; error: string | null }>) => {
      listRequestState(state, action.payload.key).error = action.payload.error
    },
    setListData: (state, action: PayloadAction<{ key: string; data: AgentExecutionSummary[] }>) => {
      listRequestState(state, action.payload.key).data = action.payload.data
    },
  },
})

export const AgentExecutionsActions = agentExecutionsSlice.actions
export const agentExecutionsReducer = agentExecutionsSlice.reducer

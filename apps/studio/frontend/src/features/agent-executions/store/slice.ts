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
  details: Record<string, AgentExecutionDetailRequestState>
}

export const initialAgentExecutionsState: AgentExecutionsState = {
  lists: {},
  details: {},
}

function listRequestState(state: AgentExecutionsState, key: string): AgentExecutionListRequestState {
  state.lists[key] ??= { data: [], loading: false, error: null }
  return state.lists[key]
}

function detailRequestState(state: AgentExecutionsState, key: string): AgentExecutionDetailRequestState {
  state.details[key] ??= { data: null, loading: false, error: null }
  return state.details[key]
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
    fetchAgentExecutionDetail: {
      reducer: () => {
        // Listener middleware owns the request.
      },
      prepare: (payload: { traceId: string; agentSpanId: string }) => ({ payload }),
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
    setDetailLoading: (state, action: PayloadAction<{ key: string; loading: boolean }>) => {
      detailRequestState(state, action.payload.key).loading = action.payload.loading
    },
    setDetailError: (state, action: PayloadAction<{ key: string; error: string | null }>) => {
      detailRequestState(state, action.payload.key).error = action.payload.error
    },
    setDetailData: (state, action: PayloadAction<{ key: string; data: AgentExecutionDetail }>) => {
      detailRequestState(state, action.payload.key).data = action.payload.data
    },
  },
})

export const AgentExecutionsActions = agentExecutionsSlice.actions
export const agentExecutionsReducer = agentExecutionsSlice.reducer

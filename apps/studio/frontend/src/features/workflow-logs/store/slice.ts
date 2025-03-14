import { createSlice } from '@reduxjs/toolkit'
import type { PayloadAction } from '@reduxjs/toolkit'
import { RootState } from '../../../root-store/store'
import { NodeLog, WorkflowLog, WorkflowMetadatum } from '../schemas'

interface LogState {
  appNames: string[]
  workflowExecutions: WorkflowMetadatum[]
  workflowLogs: { [execId: string]: WorkflowLog[] | undefined }
  nodeLogs: { [ExecID: string]: NodeLog[] | undefined }
}

const initialState: LogState = {
  appNames: [],
  workflowExecutions: [],
  workflowLogs: {},
  nodeLogs: {},
}

export const logSlice = createSlice({
  name: 'logState',
  initialState,
  reducers: {
    setAppNames: (state, action: PayloadAction<string[]>) => {
      state.appNames = action.payload
    },
    setWorkflowExecutions: (state, action: PayloadAction<WorkflowMetadatum[]>) => {
      state.workflowExecutions = action.payload
    },
    upsertWorkflowExecution: (state, action: PayloadAction<WorkflowMetadatum>) => {
      const index = state.workflowExecutions.findIndex((exec) => exec.ExecID === action.payload.ExecID)
      if (index === -1) {
        state.workflowExecutions.push(action.payload)
      } else {
        state.workflowExecutions[index] = action.payload
      }
    },
    setWorkflowLogs: (state, action: PayloadAction<{ execId: string; logs: WorkflowLog[] }>) => {
      state.workflowLogs[action.payload.execId] = action.payload.logs
    },
    setNodeLogs: (state, action: PayloadAction<{ ExecID: string; logs: NodeLog[] }>) => {
      state.nodeLogs[action.payload.ExecID] = action.payload.logs
    },
  },
})

export const LogStateActions = logSlice.actions

// Selectors
export const selectAppNames = (state: RootState) => state.logState.appNames
export const selectWorkflowExecutions = (state: RootState) => state.logState.workflowExecutions
export const selectWorkflowExecution = (state: RootState, ExecID: string) =>
  state.logState.workflowExecutions.find((exec) => exec.ExecID === ExecID)
export const selectWorkflowLogs = (state: RootState, ExecID: string) => state.logState.workflowLogs[ExecID]
export const selectNodeLogs = (state: RootState, ExecID: string) => state.logState.nodeLogs[ExecID]

// Reducer
export default logSlice.reducer

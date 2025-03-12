import { createSlice } from '@reduxjs/toolkit'
import type { PayloadAction } from '@reduxjs/toolkit'
import { RootState } from '../../../root-store/store'
import { WorkflowLog, WorkflowMetadatum } from '../schemas'

interface LogState {
  appNames: string[]
  workflowExecutions: WorkflowMetadatum[]
  workflowLogs: { [execId: string]: WorkflowLog[] | undefined }
}

const initialState: LogState = {
  appNames: [],
  workflowExecutions: [],
  workflowLogs: {},
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
  },
})

export const LogStateActions = logSlice.actions

// Selectors
export const selectAppNames = (state: RootState) => state.logState.appNames
export const selectWorkflowExecutions = (state: RootState) => state.logState.workflowExecutions
export const selectWorkflowExecution = (state: RootState, ExecID: string) =>
  state.logState.workflowExecutions.find((exec) => exec.ExecID === ExecID)
export const selectWorkflowLogs = (state: RootState, ExecID: string) => state.logState.workflowLogs[ExecID]

// Reducer
export default logSlice.reducer

import { createListenerMiddleware } from '@reduxjs/toolkit/react'
import type { AppDispatch, RootState } from '../../../root-store/store'
import { getAgentExecution } from '../fetch/get-agent-execution'
import { listAgentExecutions } from '../fetch/list-agent-executions'
import { getAgentExecutionDetailKey, getAgentExecutionQueryKey } from '../schemas/query'
import { AgentExecutionsActions } from './slice'

export const agentExecutionsListenerMiddleware = createListenerMiddleware()
const startListener = agentExecutionsListenerMiddleware.startListening.withTypes<RootState, AppDispatch>()

startListener({
  actionCreator: AgentExecutionsActions.fetchAgentExecutions,
  effect: async (action, { dispatch, getState }) => {
    const key = getAgentExecutionQueryKey(action.payload)
    if (getState().agentExecutionsState.lists[key]?.loading) return

    dispatch(AgentExecutionsActions.setListError({ key, error: null }))
    dispatch(AgentExecutionsActions.setListLoading({ key, loading: true }))

    try {
      const data = await listAgentExecutions(action.payload)
      dispatch(AgentExecutionsActions.setListData({ key, data }))
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Failed to fetch Agent executions'
      dispatch(AgentExecutionsActions.setListError({ key, error: message }))
    } finally {
      dispatch(AgentExecutionsActions.setListLoading({ key, loading: false }))
    }
  },
})

startListener({
  actionCreator: AgentExecutionsActions.fetchAgentExecutionDetail,
  effect: async (action, { dispatch, getState }) => {
    const { traceId, agentSpanId } = action.payload
    const key = getAgentExecutionDetailKey(traceId, agentSpanId)
    if (getState().agentExecutionsState.details[key]?.loading) return

    dispatch(AgentExecutionsActions.setDetailError({ key, error: null }))
    dispatch(AgentExecutionsActions.setDetailLoading({ key, loading: true }))

    try {
      const data = await getAgentExecution(traceId, agentSpanId)
      dispatch(AgentExecutionsActions.setDetailData({ key, data }))
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Failed to fetch Agent execution'
      dispatch(AgentExecutionsActions.setDetailError({ key, error: message }))
    } finally {
      dispatch(AgentExecutionsActions.setDetailLoading({ key, loading: false }))
    }
  },
})

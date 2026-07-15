import { createListenerMiddleware } from '@reduxjs/toolkit/react'
import type { AppDispatch, RootState } from '../../../root-store/store'
import { listAgentExecutions } from '../fetch/list-agent-executions'
import { getAgentExecutionQueryKey } from '../schemas/query'
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

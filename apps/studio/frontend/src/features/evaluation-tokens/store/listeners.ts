import { createListenerMiddleware } from '@reduxjs/toolkit/react'
import type { AppDispatch, RootState } from '../../../root-store/store'
import { listEvaluationTokens } from '../fetch/list-evaluation-tokens'
import { revokeEvaluationToken } from '../fetch/revoke-evaluation-token'
import { EvaluationTokensActions } from './slice'

export const evaluationTokensListenerMiddleware = createListenerMiddleware()
const startListener =
  evaluationTokensListenerMiddleware.startListening.withTypes<RootState, AppDispatch>()

startListener({
  actionCreator: EvaluationTokensActions.fetchTokens,
  effect: async ({ payload }, { dispatch, getState }) => {
    const state = getState().evaluationTokensState
    const fresh =
      state.lastUpdated !== null && Date.now() - state.lastUpdated < 2_000
    if (state.loading || (!payload.force && payload.cursor === undefined && fresh)) return

    dispatch(EvaluationTokensActions.setLoading(true))
    dispatch(EvaluationTokensActions.setError(null))
    try {
      const page = await listEvaluationTokens(payload.cursor)
      dispatch(EvaluationTokensActions.setTokens({
        items: page.items,
        nextCursor: page.next_cursor,
        append: payload.cursor !== undefined,
      }))
    } catch (error) {
      dispatch(
        EvaluationTokensActions.setError(
          error instanceof Error ? error.message : 'Failed to list evaluation tokens.',
        ),
      )
    } finally {
      dispatch(EvaluationTokensActions.setLoading(false))
    }
  },
})

startListener({
  actionCreator: EvaluationTokensActions.revokeToken,
  effect: async ({ payload }, { dispatch }) => {
    dispatch(EvaluationTokensActions.setLoading(true))
    dispatch(EvaluationTokensActions.setError(null))
    try {
      await revokeEvaluationToken(payload.id)
    } catch (error) {
      dispatch(
        EvaluationTokensActions.setError(
          error instanceof Error ? error.message : 'Failed to revoke evaluation token.',
        ),
      )
    } finally {
      dispatch(EvaluationTokensActions.setLoading(false))
      dispatch(EvaluationTokensActions.fetchTokens({ force: true }))
    }
  },
})

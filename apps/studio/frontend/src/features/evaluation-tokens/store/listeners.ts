import { createListenerMiddleware } from '@reduxjs/toolkit/react'
import type { AppDispatch, RootState } from '../../../root-store/store'
import { deleteEvaluationToken } from '../fetch/delete-evaluation-token'
import { listEvaluationTokens } from '../fetch/list-evaluation-tokens'
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
          error instanceof Error ? error.message : 'Failed to list access tokens.',
        ),
      )
    } finally {
      dispatch(EvaluationTokensActions.setLoading(false))
    }
  },
})

startListener({
  actionCreator: EvaluationTokensActions.deleteToken,
  effect: async ({ payload }, { dispatch }) => {
    dispatch(EvaluationTokensActions.setLoading(true))
    dispatch(EvaluationTokensActions.setError(null))
    try {
      await deleteEvaluationToken(payload.id)
    } catch (error) {
      dispatch(
        EvaluationTokensActions.setError(
          error instanceof Error ? error.message : 'Failed to delete access token.',
        ),
      )
    } finally {
      dispatch(EvaluationTokensActions.setLoading(false))
      dispatch(EvaluationTokensActions.fetchTokens({ force: true }))
    }
  },
})

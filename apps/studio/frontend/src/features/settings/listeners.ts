import { createListenerMiddleware } from '@reduxjs/toolkit/react'
import { SettingsStateActions } from './slice'
import { AppDispatch, RootState } from '../../root-store/store'
import { flushWal } from './fetch/flush-wal'

export const settingsStateListenerMiddleware = createListenerMiddleware()
const startListener = settingsStateListenerMiddleware.startListening.withTypes<RootState, AppDispatch>()

// FLUSH WAL
startListener({
  actionCreator: SettingsStateActions.flushWal,
  effect: async (_action, { dispatch }) => {
    dispatch(SettingsStateActions.flushWalStarted())
    try {
      const response = await flushWal()
      if (response.success) {
        dispatch(SettingsStateActions.flushWalSucceeded({ completedAt: Date.now() }))
      } else {
        dispatch(SettingsStateActions.flushWalFailed(response.message || 'Flush failed'))
      }
    } catch (e) {
      const errorMessage = e instanceof Error ? e.message : 'Unknown error'
      dispatch(SettingsStateActions.flushWalFailed(errorMessage))
    }
  },
})

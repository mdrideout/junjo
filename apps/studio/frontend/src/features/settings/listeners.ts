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
    dispatch(SettingsStateActions.setFlushWalLoading(true))
    dispatch(SettingsStateActions.setFlushWalError(null))
    dispatch(SettingsStateActions.setFlushWalSuccess(false))
    try {
      const response = await flushWal()
      if (response.success) {
        dispatch(SettingsStateActions.setFlushWalSuccess(true))
      } else {
        dispatch(SettingsStateActions.setFlushWalError(response.message || 'Flush failed'))
      }
    } catch (e) {
      const errorMessage = e instanceof Error ? e.message : 'Unknown error'
      dispatch(SettingsStateActions.setFlushWalError(errorMessage))
    } finally {
      dispatch(SettingsStateActions.setFlushWalLoading(false))
    }
  },
})

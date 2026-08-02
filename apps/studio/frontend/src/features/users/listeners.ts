import { createListenerMiddleware } from '@reduxjs/toolkit/react'

import { UsersStateActions } from './slice'
import { AppDispatch, RootState } from '../../root-store/store'
import { deleteUser } from './fetch/delete-user'
import { fetchUsers } from './fetch/list-users'

export const usersStateListenerMiddleware = createListenerMiddleware()
const startListener = usersStateListenerMiddleware.startListening.withTypes<RootState, AppDispatch>()

startListener({
  actionCreator: UsersStateActions.fetchUsersData,
  effect: async (action, { getState, dispatch }) => {
    const { force } = action.payload
    const { loading, lastUpdated } = getState().usersState

    const fresh = lastUpdated !== null && Date.now() - lastUpdated < 2_000
    if (!force && (loading || fresh)) return

    dispatch(UsersStateActions.loadStarted())
    try {
      const users = await fetchUsers()
      dispatch(UsersStateActions.loadSucceeded({ users, fetchedAt: Date.now() }))
    } catch {
      dispatch(UsersStateActions.loadFailed('Failed to load users.'))
    }
  },
})

// Listener for deleting a user
startListener({
  actionCreator: UsersStateActions.deleteUser,
  effect: async (action, { dispatch }) => {
    const { id } = action.payload

    dispatch(UsersStateActions.deleteStarted())

    try {
      await deleteUser(id)
      dispatch(UsersStateActions.deleteSucceeded())
      dispatch(UsersStateActions.fetchUsersData({ force: true }))
    } catch {
      dispatch(UsersStateActions.deleteFailed('Failed to delete user.'))
    }
  },
})

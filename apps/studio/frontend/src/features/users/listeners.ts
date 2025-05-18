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

    // Cache busting logic
    const now = Date.now()
    const staleTime = 2 * 1000 // 2 seconds
    const isStale = lastUpdated === null ? true : loading || now - lastUpdated < staleTime

    // Bail out if already loading or not stale
    if ((loading || isStale === false) && force === false) {
      console.log(`Bailing because loading is true (${loading}) or isStale is false (${isStale})`)
      return
    }

    // Clear errors and set loading
    dispatch(UsersStateActions.setError(false))
    dispatch(UsersStateActions.setLoading(true))

    // Fetch the data
    try {
      const data = await fetchUsers()
      dispatch(UsersStateActions.setUsers(data))
    } catch (error) {
      dispatch(UsersStateActions.setError(true))
    } finally {
      dispatch(UsersStateActions.setLoading(false))
    }
  },
})

// Listener for deleting a user
startListener({
  actionCreator: UsersStateActions.deleteUser,
  effect: async (action, { dispatch }) => {
    const { id } = action.payload

    dispatch(UsersStateActions.setLoading(true)) // Set loading state
    dispatch(UsersStateActions.setError(false)) // Clear any previous errors

    try {
      await deleteUser(id) // Call the API function to delete the user
      console.log(`Successfully deleted user with ID: ${id}`)
    } catch (error: any) {
      console.error(`Failed to delete user with ID: ${id}`, error)
      // Dispatch an error action, potentially with the error message
      dispatch(UsersStateActions.setError(true))
    } finally {
      // Fetch users data again to refresh the list
      dispatch(UsersStateActions.fetchUsersData({ force: true })) // Force a refresh
    }
  },
})

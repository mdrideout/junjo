import { useEffect } from 'react'
import { useAppDispatch, useAppSelector } from '../../root-store/hooks'
import { RootState } from '../../root-store/store'
import { UsersStateActions } from './slice'
import { TrashIcon } from '@heroicons/react/24/outline'
import CreateUserDialog from './CreateUserDialog'

export default function UsersPage() {
  const dispatch = useAppDispatch()
  const { users, loading, error } = useAppSelector((state: RootState) => state.usersState)

  // Fetch users data when the component mounts
  useEffect(() => {
    dispatch(UsersStateActions.fetchUsersData({ force: false }))
  }, [dispatch])

  // Handle loading and error states
  if (loading) {
    return <div className={'h-full w-full flex items-center justify-center'}>Loading...</div>
  }
  // Render the users list
  return (
    <div className="flex h-dvh flex-col overflow-y-auto px-5 py-6">
      <div>
        <h1>Users</h1>
        <p className="mt-1 text-sm text-[var(--studio-text-muted)]">
          Create and manage user accounts.
        </p>
      </div>
      <hr className="my-4" />
      <div>
        <CreateUserDialog />
      </div>
      {error !== null && (
        <p role="alert" className="mt-4 text-sm text-red-700 dark:text-red-300">
          {error}
        </p>
      )}
      <div className="mt-4 shrink-0 overflow-x-auto">
        <table className="w-full max-w-[1024px] text-left text-sm">
          <thead>
            <tr className="border-b border-[var(--studio-border)]">
              <th className="px-3 py-2">ID</th>
              <th className="px-3 py-2">Email</th>
              <th className="px-3 py-2">Created</th>
              <th className="px-3 py-2">
                <span className="sr-only">Actions</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {users.map((user) => {
              // Make date human readable
              const createdAt = new Date(user.created_at)
              const createdAtString = createdAt.toLocaleString()

              return (
                <tr
                  key={user.id}
                  className="border-b border-[var(--studio-border)] last:border-0"
                >
                  <td className="px-3 py-3 font-mono">{user.id}</td>
                  <td className="px-3 py-3 font-medium">{user.email}</td>
                  <td className="px-3 py-3">{createdAtString}</td>
                  <td className="px-3 py-3 text-right">
                    <div className="flex justify-end gap-2">
                      <button
                        type="button"
                        aria-label={`Delete user ${user.email}`}
                        className="rounded-md p-1 hover:bg-[var(--studio-surface-hover)]"
                        onClick={() => {
                          if (confirm(`Are you sure you want to delete user ${user.email}?`)) {
                            dispatch(UsersStateActions.deleteUser({ id: user.id }))
                          }
                        }}
                      >
                        <TrashIcon className="size-4" />
                      </button>
                    </div>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}

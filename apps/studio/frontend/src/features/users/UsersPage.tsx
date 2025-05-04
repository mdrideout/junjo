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
  if (error) {
    return <div className={'h-full w-full flex items-center justify-center'}>Error: {error}</div>
  }

  // Render the users list
  return (
    <div className={'px-3 py-4 flex flex-col h-dvh overflow-hidden'}>
      <div className={'flex gap-x-3 px-2 items-center'}>
        <div className={'flex gap-x-3 font-bold'}>Users</div>
        <CreateUserDialog />
      </div>
      <hr className={'my-4'} />
      <div className={'px-2'}>
        <table className="text-left text-sm">
          <thead>
            <tr>
              <th className={'px-4 py-1'}>ID</th>
              <th className={'px-4 py-1'}>Email</th>
              <th className={'px-4 py-1'}>Created At</th>
              <th className={'px-4 py-1'}></th>
            </tr>
          </thead>
          <tbody>
            {users.map((user) => {
              // Make date human readable
              const createdAt = new Date(user.CreatedAt)
              const createdAtString = createdAt.toLocaleString()

              return (
                <tr
                  key={user.ID}
                  className={'last-of-type:border-0 border-b border-zinc-200 dark:border-zinc-600'}
                >
                  <td className={'px-4 py-1.5 font-mono'}>{user.ID}</td>
                  <td className={'px-4 py-1.5'}>{user.Email}</td>
                  <td className={'px-4 py-1.5 font-mono'}>{createdAtString}</td>
                  <td className={' text-center'}>
                    <button
                      className={'p-1 hover:bg-zinc-300 dark:hover:bg-zinc-700 rounded-md cursor-pointer'}
                      onClick={() => {
                        if (confirm(`Are you sure you want to delete user ${user.Email}?`)) {
                          dispatch(UsersStateActions.deleteUser({ id: user.ID }))
                        }
                      }}
                    >
                      <TrashIcon className={'size-4'} />
                    </button>
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

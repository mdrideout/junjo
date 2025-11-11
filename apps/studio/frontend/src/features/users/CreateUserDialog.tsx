import { useState } from 'react'
import { Button } from '../../components/catalyst/button'
import {
  Dialog,
  DialogActions,
  DialogBody,
  DialogDescription,
  DialogTitle,
} from '../../components/catalyst/dialog'
import { UserPlusIcon } from '@heroicons/react/24/solid'
import { useAppDispatch } from '../../root-store/hooks'
import { UsersStateActions } from './slice'
import { getApiHost } from '../../config'

export default function CreateUserDialog() {
  const dispatch = useAppDispatch()
  let [isOpen, setIsOpen] = useState(false)

  // Loading and error states
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Handle form submission
  const handleSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault()

    setLoading(true)
    setError(null)

    const formData = new FormData(event.currentTarget)
    const email = formData.get('email') as string
    const password = formData.get('password') as string

    // Perform setup
    try {
      const endpoint = '/users'
      const response = await fetch(`${getApiHost(endpoint)}${endpoint}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password }),
        credentials: 'include',
      })

      if (!response.ok) {
        const errorData = await response.json()
        console.log('Reason: ', errorData)

        if (response.status === 409) {
          throw new Error('User already exists.')
        } else if (response.status === 400) {
          throw new Error(errorData.detail || 'Invalid request.')
        } else {
          throw new Error('User creation failed. Please check server logs.')
        }
      }

      // Refresh the users list
      dispatch(UsersStateActions.fetchUsersData({ force: true }))
      setIsOpen(false)
    } catch (err: any) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <>
      <button
        className={
          'px-2 py-1 text-xs cursor-pointer font-bold flex gap-x-2 items-center bg-zinc-200 hover:bg-zinc-300 dark:bg-zinc-700 dark:hover:bg-zinc-600 rounded-md'
        }
        onClick={() => {
          setIsOpen(true)
        }}
      >
        <UserPlusIcon className={'size-4'} /> Create User
      </button>
      <Dialog open={isOpen} onClose={setIsOpen}>
        <DialogTitle>Create User</DialogTitle>
        <DialogDescription>
          This user will have complete access. There are currently no roles or permissions.
        </DialogDescription>
        <DialogBody>
          <form onSubmit={handleSubmit} className="">
            <div className="flex flex-col gap-y-2">
              <input type="hidden" name="actionType" value="signIn" />
              <input
                type="email"
                name="email"
                placeholder="Email address"
                required
                className="py-1 px-2 rounded-sm border border-zinc-300 dark:border-zinc-600"
              />
              <input
                type="password"
                name="password"
                placeholder="Password"
                autoComplete="current-password"
                required
                className="py-1 px-2 rounded-sm border border-zinc-300 dark:border-zinc-600"
              />
              {error && <p className="text-red-700 dark:text-red-300">{error}</p>}
            </div>
            <DialogActions>
              <Button plain onClick={() => setIsOpen(false)}>
                Cancel
              </Button>
              <Button disabled={loading} type="submit">
                Create User
              </Button>
            </DialogActions>
          </form>
        </DialogBody>
      </Dialog>
    </>
  )
}

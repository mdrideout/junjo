import { useState } from 'react'
import { Button } from '../../components/catalyst/button'
import {
  Dialog,
  DialogActions,
  DialogBody,
  DialogDescription,
  DialogTitle,
} from '../../components/catalyst/dialog'
import { useAppDispatch } from '../../root-store/hooks'
import { PlusIcon } from '@heroicons/react/24/outline'
import { ApiKeysStateActions } from './slice'

export default function CreateApiKeyDialog() {
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
    const name = formData.get('name') as string

    // Perform setup
    try {
      const response = await fetch('http://localhost:1323/api_keys', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name }),
        credentials: 'include',
      })

      const responseData = await response.json()

      if (!response.ok) {
        console.error('API Key Creation Failed: ', responseData)

        throw new Error('API Key Creation Failed.')
      }

      // Refresh the list
      dispatch(ApiKeysStateActions.fetchApiKeysData({ force: true }))
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
        <PlusIcon className={'size-4'} /> Create API Key
      </button>
      <Dialog open={isOpen} onClose={setIsOpen}>
        <DialogTitle>Create API Key</DialogTitle>
        <DialogDescription>
          This API key will allow Junjo instances to deliver telemetry to this server.
        </DialogDescription>
        <DialogBody>
          <form onSubmit={handleSubmit} className="">
            <div className="flex flex-col gap-y-2">
              <input type="hidden" name="actionType" value="createApiKey" />
              <input
                type="name"
                name="name"
                placeholder="Name"
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

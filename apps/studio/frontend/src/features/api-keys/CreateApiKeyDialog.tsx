import { useState, useEffect } from 'react'
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
import { getApiHost } from '../../config'

export default function CreateApiKeyDialog() {
  const dispatch = useAppDispatch()
  const [isOpen, setIsOpen] = useState(false)

  // Loading and error states
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Reset error and loading states when dialog opens/closes
  useEffect(() => {
    if (!isOpen) {
      setError(null)
      setLoading(false)
    }
  }, [isOpen])

  // Handle form submission
  const handleSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault()

    setLoading(true)
    setError(null)

    const formData = new FormData(event.currentTarget)
    const name = formData.get('name') as string

    // Perform setup
    try {
      const apiHost = getApiHost('/api_keys')
      const response = await fetch(`${apiHost}/api_keys`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name }),
        credentials: 'include',
      })

      const responseData = await response.json()

      if (!response.ok) {
        console.log('Error response:', responseData)

        // Try detail field (handles both Pydantic array and custom string)
        if (responseData.detail) {
          if (Array.isArray(responseData.detail)) {
            // Pydantic validation errors (422)
            const errors = responseData.detail
              .map((err: any) => err.msg || err.message)
              .join('. ')
            throw new Error(errors || 'Validation failed.')
          }
          // Custom error string (400, 409, etc.)
          throw new Error(responseData.detail)
        }

        // Try message field (fallback)
        if (responseData.message) {
          throw new Error(responseData.message)
        }

        // Final fallback with status code
        throw new Error(`Request failed (${response.status})`)
      }

      // Refresh the list
      dispatch(ApiKeysStateActions.fetchApiKeysData({ force: true }))
      setIsOpen(false)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'An error occurred')
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
                data-autofocus
                name="name"
                placeholder="Key Name"
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
                Create Key
              </Button>
            </DialogActions>
          </form>
        </DialogBody>
      </Dialog>
    </>
  )
}

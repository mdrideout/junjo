import { useState, useEffect } from 'react'
import { ActionButton } from '../../components/actions/action-button'
import { Modal, ModalFooter } from '../../components/overlays/modal'
import { useAppDispatch } from '../../root-store/hooks'
import { PlusIcon } from '@heroicons/react/24/outline'
import { ApiKeysStateActions } from './slice'
import { getApiHost } from '../../config'

interface ApiErrorResponse {
  detail?: string | Array<{ msg?: string; message?: string }>
  message?: string
}

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
      const apiHost = getApiHost()
      const response = await fetch(`${apiHost}/api_keys`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name }),
        credentials: 'include',
      })

      const responseData = (await response.json()) as ApiErrorResponse

      if (!response.ok) {
        console.log('Error response:', responseData)

        // Try detail field (handles both Pydantic array and custom string)
        if (responseData.detail) {
          if (Array.isArray(responseData.detail)) {
            // Pydantic validation errors (422)
            const errors = responseData.detail.map((err) => err.msg || err.message).join('. ')
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
      <ActionButton
        size="compact"
        intent="secondary"
        onClick={() => {
          setIsOpen(true)
        }}
      >
        <PlusIcon className={'size-4'} /> Create API Key
      </ActionButton>
      <Modal
        open={isOpen}
        onOpenChange={setIsOpen}
        title="Create API Key"
        description="This API key will allow Junjo instances to deliver telemetry to this server."
      >
        <form onSubmit={handleSubmit}>
          <div className="flex flex-col gap-4">
            <input type="hidden" name="actionType" value="createApiKey" />
            <label className="flex flex-col gap-1.5 text-sm font-medium">
              Key name
              <input
                name="name"
                placeholder="Key Name"
                required
                className="rounded-lg border border-[var(--studio-border-strong)] bg-[var(--studio-surface-raised)] px-3 py-2 font-normal outline-none focus:border-[var(--studio-focus-ring)]"
              />
            </label>
            {error && (
              <p role="alert" className="text-sm text-red-700 dark:text-red-300">
                {error}
              </p>
            )}
          </div>
          <ModalFooter>
            <ActionButton intent="secondary" onClick={() => setIsOpen(false)}>
              Cancel
            </ActionButton>
            <ActionButton disabled={loading} type="submit">
              Create Key
            </ActionButton>
          </ModalFooter>
        </form>
      </Modal>
    </>
  )
}

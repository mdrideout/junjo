import { useState, useEffect } from 'react'
import { ActionButton } from '../../components/actions/action-button'
import { Modal, ModalFooter } from '../../components/overlays/modal'
import { useAppDispatch } from '../../root-store/hooks'
import { PlusIcon } from '@heroicons/react/24/outline'
import { ApiKeysStateActions } from './slice'
import { getApiHost } from '../../config'
import {
  ApiKeyCreateResponseSchema,
  type ApiKeyCreateResponse,
} from './response-schemas'

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
  const [created, setCreated] = useState<ApiKeyCreateResponse | null>(null)

  // Reset error and loading states when dialog opens/closes
  useEffect(() => {
    if (!isOpen) {
      setError(null)
      setLoading(false)
      setCreated(null)
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

      const responseData: unknown = await response.json()

      if (!response.ok) {
        const errorResponse = responseData as ApiErrorResponse
        console.log('Error response:', responseData)

        // Try detail field (handles both Pydantic array and custom string)
        if (errorResponse.detail) {
          if (Array.isArray(errorResponse.detail)) {
            // Pydantic validation errors (422)
            const errors = errorResponse.detail.map((err) => err.msg || err.message).join('. ')
            throw new Error(errors || 'Validation failed.')
          }
          // Custom error string (400, 409, etc.)
          throw new Error(errorResponse.detail)
        }

        // Try message field (fallback)
        if (errorResponse.message) {
          throw new Error(errorResponse.message)
        }

        // Final fallback with status code
        throw new Error(`Request failed (${response.status})`)
      }

      setCreated(ApiKeyCreateResponseSchema.parse(responseData))

      // Refresh the list
      dispatch(ApiKeysStateActions.fetchApiKeysData({ force: true }))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'An error occurred')
    } finally {
      setLoading(false)
    }
  }

  const copyApiKey = async () => {
    if (created === null) return
    try {
      await navigator.clipboard.writeText(created.key)
    } catch {
      setError('The API key could not be copied. Copy it manually before closing.')
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
        <PlusIcon className={'size-4'} /> Create telemetry API key
      </ActionButton>
      <Modal
        open={isOpen}
        onOpenChange={setIsOpen}
        title="Create telemetry API key"
      >
        {created === null ? (
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
                Create API key
              </ActionButton>
            </ModalFooter>
          </form>
        ) : (
          <div className="flex flex-col gap-4">
            <p className="text-sm text-[var(--studio-text-muted)]">
              API key created. You can copy it again later from API Keys.
            </p>
            <code className="break-all rounded-lg border border-[var(--studio-border)] bg-[var(--studio-surface-raised)] p-3 text-sm">
              {created.key}
            </code>
            {error && (
              <p role="alert" className="text-sm text-red-700 dark:text-red-300">
                {error}
              </p>
            )}
            <ModalFooter>
              <ActionButton intent="secondary" onClick={copyApiKey}>
                Copy API key
              </ActionButton>
              <ActionButton onClick={() => setIsOpen(false)}>Done</ActionButton>
            </ModalFooter>
          </div>
        )}
      </Modal>
    </>
  )
}

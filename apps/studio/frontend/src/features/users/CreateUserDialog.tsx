import { useState } from 'react'
import { UserPlusIcon } from '@heroicons/react/24/solid'
import { ActionButton } from '../../components/actions/action-button'
import { Modal, ModalFooter } from '../../components/overlays/modal'
import { useAppDispatch } from '../../root-store/hooks'
import { UsersStateActions } from './slice'
import { getApiHost } from '../../config'

interface ApiErrorResponse {
  detail?: string | Array<{ msg?: string; message?: string }>
  message?: string
}

export default function CreateUserDialog() {
  const dispatch = useAppDispatch()
  const [isOpen, setIsOpen] = useState(false)

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
      const response = await fetch(`${getApiHost()}${endpoint}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password }),
        credentials: 'include',
      })

      if (!response.ok) {
        const errorData = (await response.json()) as ApiErrorResponse
        console.log('Error response:', errorData)

        // Try detail field (handles both Pydantic array and custom string)
        if (errorData.detail) {
          if (Array.isArray(errorData.detail)) {
            // Pydantic validation errors (422)
            const errors = errorData.detail.map((err) => err.msg || err.message).join('. ')
            throw new Error(errors || 'Validation failed.')
          }
          // Custom error string (400, 409, etc.)
          throw new Error(errorData.detail)
        }

        // Try message field (fallback)
        if (errorData.message) {
          throw new Error(errorData.message)
        }

        // Final fallback with status code
        throw new Error(`Request failed (${response.status})`)
      }

      // Refresh the users list
      dispatch(UsersStateActions.fetchUsersData({ force: true }))
      setIsOpen(false)
    } catch (err: unknown) {
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
        <UserPlusIcon className={'size-4'} /> Create User
      </ActionButton>
      <Modal
        open={isOpen}
        onOpenChange={setIsOpen}
        title="Create User"
        description="This user will have complete access. There are currently no roles or permissions."
      >
        <form onSubmit={handleSubmit}>
          <div className="flex flex-col gap-4">
            <input type="hidden" name="actionType" value="signIn" />
            <label className="flex flex-col gap-1.5 text-sm font-medium">
              Email address
              <input
                type="email"
                name="email"
                placeholder="Email address"
                required
                className="rounded-lg border border-[var(--studio-border-strong)] bg-[var(--studio-surface-raised)] px-3 py-2 font-normal outline-none focus:border-[var(--studio-focus-ring)]"
              />
            </label>
            <label className="flex flex-col gap-1.5 text-sm font-medium">
              Password
              <input
                type="password"
                name="password"
                placeholder="Password"
                autoComplete="new-password"
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
              Create User
            </ActionButton>
          </ModalFooter>
        </form>
      </Modal>
    </>
  )
}

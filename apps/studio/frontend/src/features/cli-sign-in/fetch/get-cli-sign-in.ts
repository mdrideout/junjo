import { readApiError } from '../../../auth/api-error'
import { CliSignInReadSchema, type CliSignInRead } from '../schemas'

/**
 * The pending CLI sign-in with this user code, or null when Studio has none:
 * the code is unknown, already used, or expired (404), or it is not a code
 * Studio issues (422).
 */
export async function getCliSignIn(
  userCode: string,
  signal?: AbortSignal,
): Promise<CliSignInRead | null> {
  const response = await fetch(
    `/api/v1/cli-sign-ins/${encodeURIComponent(userCode)}`,
    { credentials: 'include', signal },
  )
  if (response.status === 404 || response.status === 422) return null
  if (!response.ok) {
    throw new Error(await readApiError(response, 'Failed to load CLI sign-in'))
  }
  return CliSignInReadSchema.parse(await response.json())
}

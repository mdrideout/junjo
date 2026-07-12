import { fetchApiKeys } from '../features/api-keys/fetch/list-api-keys'

/**
 * Determines the post-sign-in navigation destination.
 *
 * If user has no API keys, navigates to /api-keys to prompt creation.
 * Otherwise navigates to home page.
 *
 * @returns Promise resolving to the destination path
 */
export async function getPostSignInDestination(): Promise<string> {
  console.log('[getPostSignInDestination] Starting API key check...')
  try {
    const apiKeys = await fetchApiKeys()
    console.log('[getPostSignInDestination] Fetched API keys:', apiKeys.length, 'keys')
    const destination = apiKeys.length === 0 ? '/api-keys' : '/'
    console.log('[getPostSignInDestination] Navigating to:', destination)
    return destination
  } catch (error) {
    console.error('[getPostSignInDestination] Failed to check API keys, defaulting to home:', error)
    return '/' // Default to home on error
  }
}

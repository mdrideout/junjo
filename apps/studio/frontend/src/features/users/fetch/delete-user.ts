/**
 * Deletes a user by their ID.
 * @param id The ID of the user to delete.
 * @throws Will throw an error if the fetch request fails.
 */
import { API_HOST } from '../../../config'

export const deleteUser = async (id: number): Promise<void> => {
  const response = await fetch(`${API_HOST}/users/${id}`, {
    method: 'DELETE',
    credentials: 'include',
    headers: {
      Accept: 'application/json', // Optional: Specify what response type you accept if any
    },
  })

  if (!response.ok) {
    // Attempt to get more specific error info from the response body if available
    let errorDetails = response.statusText
    try {
      const errorData = await response.json()
      errorDetails = errorData.message || errorDetails // Use message from response if present
    } catch (e) {
      // Ignore if response body is not JSON or empty
    }
    throw new Error(`deleteUser failed for ID ${id}: ${errorDetails} (Status: ${response.status})`)
  }

  // DELETE requests often return 204 No Content, so no response body to parse.
  console.log(`User with ID ${id} deleted successfully.`)
}

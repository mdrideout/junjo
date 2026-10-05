import z from 'zod'

export const fetchServiceNames = async (): Promise<string[]> => {
  // Use the backend's service discovery endpoint
  const endpoint = '/api/v1/observability/services'

  const response = await fetch(endpoint, {
    method: 'GET',
    credentials: 'include',
    headers: {
      Accept: 'application/json',
    },
  })

  if (!response.ok) {
    throw new Error(`fetchServiceNames failed: ${response.statusText}`)
  }

  const data = await response.json()

  // Validate the response data against our schema
  try {
    // Validate the data is an array of strings
    return z.string().array().parse(data)
  } catch (error) {
    console.error('Data validation error:', error)
    throw new Error('Invalid data received from server')
  }
}

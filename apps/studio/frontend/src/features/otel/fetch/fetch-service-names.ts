import z from 'zod'

export const fetchServiceNames = async (): Promise<string[]> => {
  const response = await fetch(`http://localhost:1323/otel/span-service-names`, {
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

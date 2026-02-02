import { z } from 'zod'
import { ContactRead, ContactReadSchema, CreateSetupContactResponse, CreateSetupContactResponseSchema, Sex } from './schemas'

export const createSetupContact = async (sex?: Sex): Promise<CreateSetupContactResponse> => {
  const url = new URL('http://127.0.0.1:8000/api/contact')
  if (sex) {
    url.searchParams.set('sex', sex)
  }

  const response = await fetch(url.toString(), {
    method: 'POST',
    mode: 'cors',
    headers: {
      'Content-Type': 'application/json',
    },
  })

  if (!response.ok) {
    throw new Error(`Failed to create setup contact: ${response.statusText}`)
  }

  const data = await response.json()

  try {
    // Validate the response data against our schema
    return CreateSetupContactResponseSchema.parse(data)
  } catch (error) {
    console.error('Data validation error:', error)
    throw new Error('Invalid data received from server')
  }
}

export const getAllContacts = async (): Promise<ContactRead[]> => {
  const response = await fetch('http://127.0.0.1:8000/api/contact', {
    method: 'GET',
    mode: 'cors',
    headers: {
      'Content-Type': 'application/json',
    },
  })

  if (!response.ok) {
    throw new Error(`Failed to fetch contacts: ${response.statusText}`)
  }

  const data = await response.json()
  console.log('Data received from server:', data)

  try {
    // Validate the response data as an array of ContactRead
    return z.array(ContactReadSchema).parse(data)
  } catch (error) {
    console.error('Data validation error:', error)
    throw new Error('Invalid data received from server')
  }
}

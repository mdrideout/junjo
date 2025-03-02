import { z } from 'zod'
import { ContactRead, ContactReadSchema, GenderEnum } from './schemas'

export interface CreateContactRequest {
  gender: GenderEnum
}

export const createContact = async (request: CreateContactRequest): Promise<ContactRead> => {
  const response = await fetch(`http://127.0.0.1:8000/workflows/contact`, {
    method: 'POST',
    body: JSON.stringify(request),
    mode: 'cors',
    headers: {
      'Content-Type': 'application/json',
    },
  })

  if (!response.ok) {
    throw new Error(`Failed to fetch workflow logs: ${response.statusText}`)
  }

  const data = await response.json()

  try {
    // Validate the response data against our schema
    return ContactReadSchema.parse(data)
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

  try {
    // Validate the response data as an array of ContactRead
    return z.array(ContactReadSchema).parse(data)
  } catch (error) {
    console.error('Data validation error:', error)
    throw new Error('Invalid data received from server')
  }
}

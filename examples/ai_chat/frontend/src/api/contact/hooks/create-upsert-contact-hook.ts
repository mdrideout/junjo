import { useState } from 'react'
import { createContact } from '../fetch'
import { GenderEnum } from '../schemas'
import { useContactStore } from '../store'

interface UseCreateContactResult {
  isLoading: boolean
  error: string | null
  createContact: (gender: GenderEnum) => Promise<void> // Added createContact function
}

const useCreateAndUpsertContact = (): UseCreateContactResult => {
  const { upsertContacts } = useContactStore()
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const createContactAndUpsert = async (gender: GenderEnum) => {
    setIsLoading(true)
    setError(null)
    try {
      // Create and upsert the new contact into state
      const newContact = await createContact({ gender })
      upsertContacts([newContact])
    } catch (error: any) {
      setError(error.message)
    } finally {
      setIsLoading(false)
    }
  }

  return { isLoading, error, createContact: createContactAndUpsert }
}

export default useCreateAndUpsertContact

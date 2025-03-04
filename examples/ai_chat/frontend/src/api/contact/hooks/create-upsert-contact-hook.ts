import { useState } from 'react'
import { createSetupContact } from '../fetch'
import { GenderEnum } from '../schemas'
import { useContactStore } from '../store'
import { useChatsWithMembersStore } from '../../chat/store'

interface UseCreateContactResult {
  isLoading: boolean
  error: string | null
  createContact: (gender: GenderEnum) => Promise<void> // Added createContact function
}

const useCreateAndUpsertContact = (): UseCreateContactResult => {
  const { upsertContacts } = useContactStore()
  const { upsertChat } = useChatsWithMembersStore()
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const createContactAndUpsert = async (gender: GenderEnum) => {
    setIsLoading(true)
    setError(null)
    try {
      // Create and upsert the new contact into state
      const response = await createSetupContact({ gender })
      upsertContacts([response.contact])
      upsertChat(response.chat_with_members)
    } catch (error: any) {
      setError(error.message)
    } finally {
      setIsLoading(false)
    }
  }

  return { isLoading, error, createContact: createContactAndUpsert }
}

export default useCreateAndUpsertContact

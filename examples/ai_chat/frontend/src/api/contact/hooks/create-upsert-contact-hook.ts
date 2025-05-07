import { useState } from 'react'
import { createSetupContact } from '../fetch'
import { useContactStore } from '../store'
import { useChatsWithMembersStore } from '../../chat/store'

interface UseCreateContactResult {
  isLoading: boolean
  error: string | null
  createContact: () => Promise<string> // Added createContact function
}

const useCreateAndUpsertContact = (): UseCreateContactResult => {
  const { upsertContacts } = useContactStore()
  const { upsertChat } = useChatsWithMembersStore()
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const createContactAndUpsert = async (): Promise<string> => {
    setIsLoading(true)
    setError(null)
    try {
      // Create and upsert the new contact into state
      const response = await createSetupContact()
      upsertContacts([response.contact])
      upsertChat(response.chat_with_members)

      return response.chat_with_members.id
    } catch (error: any) {
      setError(error.message)
      throw error
    } finally {
      setIsLoading(false)
    }
  }

  return { isLoading, error, createContact: createContactAndUpsert }
}

export default useCreateAndUpsertContact

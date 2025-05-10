import { useState, useEffect } from 'react'
import { getAllContacts } from '../fetch'
import { useContactStore } from '../store'

interface UseGetContactsResult {
  isLoading: boolean
  error: string | null
  refetch: () => Promise<void>
}

const useGetContacts = (): UseGetContactsResult => {
  const { lastFetch, upsertContacts } = useContactStore()
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Cache duration
  const CACHE_DURATION = 3 * 1000 // 3 seconds

  const fetchContacts = async () => {
    console.log('Fetching contacts...')
    if (lastFetch && Date.now() - lastFetch < CACHE_DURATION) return

    setIsLoading(true)
    setError(null)
    try {
      const fetchedContacts = await getAllContacts()
      upsertContacts(fetchedContacts)
      console.log('Upserted contacts:', fetchedContacts)
    } catch (error: any) {
      setError(error.message)
    } finally {
      setIsLoading(false)
    }
  }

  // Automatically run
  useEffect(() => {
    fetchContacts()
  }, [])

  return { isLoading, error, refetch: fetchContacts }
}

export default useGetContacts

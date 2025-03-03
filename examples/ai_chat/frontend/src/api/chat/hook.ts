import { useState, useEffect } from 'react'
import { fetchChatsWithMembers } from './fetch'
import { useChatsWithMembersStore } from './store'

interface UseGetContactsResult {
  isLoading: boolean
  error: string | null
  refetch: () => Promise<void>
}

const useGetChatsWithMembers = (): UseGetContactsResult => {
  const { lastFetch, set } = useChatsWithMembersStore()
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Cache duration
  const CACHE_DURATION = 3 * 1000 // 3 seconds

  const fetchData = async () => {
    if (lastFetch && Date.now() - lastFetch < CACHE_DURATION) return

    setIsLoading(true)
    setError(null)
    try {
      const data = await fetchChatsWithMembers()
      set(data)
    } catch (error: any) {
      setError(error.message)
    } finally {
      setIsLoading(false)
    }
  }

  // Automatically run
  useEffect(() => {
    fetchData()
  }, [])

  return { isLoading, error, refetch: fetchData }
}

export default useGetChatsWithMembers

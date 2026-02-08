import { useState, useEffect } from 'react'
import { fetchChatsWithMembers } from './fetch'
import { useChatsWithMembersStore } from './store'
import { useChatReadStateStore } from './read-store'

interface UseGetContactsResult {
  isLoading: boolean
  error: string | null
  refetch: () => Promise<void>
}

const useGetChatsWithMembers = (): UseGetContactsResult => {
  const { set } = useChatsWithMembersStore()
  const initializeFromChats = useChatReadStateStore((state) => state.initializeFromChats)
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Cache duration
  const CACHE_DURATION = 3 * 1000 // 3 seconds
  const POLL_INTERVAL = 7500

  const fetchData = async () => {
    const lastFetch = useChatsWithMembersStore.getState().lastFetch
    if (lastFetch && Date.now() - lastFetch < CACHE_DURATION) return

    setIsLoading(true)
    setError(null)
    try {
      const data = await fetchChatsWithMembers()
      set(data)
      initializeFromChats(data)
    } catch (error: any) {
      setError(error.message)
    } finally {
      setIsLoading(false)
    }
  }

  // Automatically run
  useEffect(() => {
    fetchData()

    const intervalId = window.setInterval(fetchData, POLL_INTERVAL)
    return () => window.clearInterval(intervalId)
  }, [])

  return { isLoading, error, refetch: fetchData }
}

export default useGetChatsWithMembers

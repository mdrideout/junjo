import { create } from 'zustand'
import { devtools } from 'zustand/middleware'
import { ChatWithMembersRead } from './schemas'

interface ContactState {
  chats: ChatWithMembersRead[]
  lastFetch: number | null

  set: (chats: ChatWithMembersRead[]) => void
}

export const useChatsWithMembersStore = create<ContactState>()(
  devtools((set) => ({
    chats: [],
    lastFetch: null,

    set: (chats) => set({ chats, lastFetch: Date.now() }),
  }))
)

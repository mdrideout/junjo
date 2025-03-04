import { create } from 'zustand'
import { devtools } from 'zustand/middleware'
import { ChatWithMembersRead } from './schemas'

interface ContactState {
  chats: ChatWithMembersRead[]
  lastFetch: number | null

  set: (chats: ChatWithMembersRead[]) => void
  upsertChat: (chat: ChatWithMembersRead) => void
}

export const useChatsWithMembersStore = create<ContactState>()(
  devtools((set) => ({
    chats: [],
    lastFetch: null,

    set: (chats) => set({ chats, lastFetch: Date.now() }),

    upsertChat: (chat) =>
      set((state) => {
        // Check if the chat already exists
        const index = state.chats.findIndex((c) => c.id === chat.id)
        if (index === -1) {
          // If it doesn't, add it
          state.chats.push(chat)
        } else {
          // If it does, update it
          state.chats[index] = chat
        }

        // Sort for most recent first
        state.chats.sort((a, b) => b.last_message_time.getTime() - a.last_message_time.getTime())

        return { chats: state.chats }
      }),
  }))
)

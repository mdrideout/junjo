import { create } from 'zustand'
import { devtools } from 'zustand/middleware'
import { ChatWithMembersRead } from './schemas'

interface ContactState {
  chats: ChatWithMembersRead[]
  lastFetch: number | null

  set: (chats: ChatWithMembersRead[]) => void
  upsertChat: (chat: ChatWithMembersRead) => void
  touchChat: (chat_id: string, last_message_time: Date) => void
}

export const useChatsWithMembersStore = create<ContactState>()(
  devtools((set) => ({
    chats: [],
    lastFetch: null,

    set: (chats) =>
      set({
        chats: [...chats].sort((a, b) => b.last_message_time.getTime() - a.last_message_time.getTime()),
        lastFetch: Date.now(),
      }),

    upsertChat: (chat) =>
      set((state) => {
        const index = state.chats.findIndex((c) => c.id === chat.id)
        const next = [...state.chats]
        if (index === -1) next.push(chat)
        else next[index] = chat

        next.sort((a, b) => b.last_message_time.getTime() - a.last_message_time.getTime())
        return { chats: next }
      }),

    touchChat: (chat_id, last_message_time) =>
      set((state) => {
        const next = state.chats.map((chat) => {
          if (chat.id !== chat_id) return chat
          if (chat.last_message_time.getTime() >= last_message_time.getTime()) return chat
          return { ...chat, last_message_time }
        })

        next.sort((a, b) => b.last_message_time.getTime() - a.last_message_time.getTime())
        return { chats: next }
      }),
  }))
)

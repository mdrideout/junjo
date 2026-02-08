import { create } from 'zustand'
import { createJSONStorage, devtools, persist } from 'zustand/middleware'

import { ChatWithMembersRead } from './schemas'

interface ChatReadState {
  lastReadAtByChatId: Record<string, number>

  initializeFromChats: (chats: ChatWithMembersRead[]) => void
  markChatRead: (chatId: string, at?: number) => void
}

export const useChatReadStateStore = create<ChatReadState>()(
  devtools(
    persist(
      (set) => ({
        lastReadAtByChatId: {},

        initializeFromChats: (chats) =>
          set((state) => {
            const next = { ...state.lastReadAtByChatId }
            for (const chat of chats) {
              if (next[chat.id] == null) {
                next[chat.id] = chat.last_message_time.getTime()
              }
            }
            return { lastReadAtByChatId: next }
          }),

        markChatRead: (chatId, at) =>
          set((state) => ({
            lastReadAtByChatId: { ...state.lastReadAtByChatId, [chatId]: at ?? Date.now() },
          })),
      }),
      {
        name: 'ai-chat:last-read-at',
        storage: createJSONStorage(() => localStorage),
      }
    )
  )
)


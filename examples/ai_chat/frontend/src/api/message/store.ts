import { create } from 'zustand'
import { devtools } from 'zustand/middleware'
import { MessageRead } from './schemas'

interface MessageState {
  messages: Partial<{ [id: string]: MessageRead }>

  upsertMessages: (messages: MessageRead[]) => void
}

export const useChatsWithMembersStore = create<MessageState>()(
  devtools((set) => ({
    messages: {},

    upsertMessages: (list: MessageRead[]) =>
      set((state) => {
        const newMessages = { ...state.messages }
        list.forEach((item) => {
          newMessages[item.id] = item
        })
        return { messages: newMessages }
      }),
  }))
)

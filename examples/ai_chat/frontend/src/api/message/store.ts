import { create } from 'zustand'
import { devtools } from 'zustand/middleware'
import { MessageRead } from './schemas'

interface MessageState {
  messages: Partial<{ [chat_id: string]: { [message_id: string]: MessageRead } }>

  upsertMessages: (chat_id: string, messages: MessageRead[]) => void
}

export const useMessagesStore = create<MessageState>()(
  devtools((set) => ({
    messages: {},

    upsertMessages: (chat_id: string, list: MessageRead[]) =>
      set((state) => {
        const chatIdMessages = state.messages[chat_id] || {}
        const newMessages = { ...chatIdMessages }
        list.forEach((item) => {
          newMessages[item.id] = item
        })

        state.messages[chat_id] = newMessages

        return {
          messages: { ...state.messages },
        }
      }),
  }))
)

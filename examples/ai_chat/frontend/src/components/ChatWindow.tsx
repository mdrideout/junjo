import { useEffect, useRef, useState } from 'react'
import { useMessagesStore } from '../api/message/store'
import ChatReceiveBubble from './bubbles/ChatReceiveBubble'
import ChatSendBubble from './bubbles/ChatSendBubble'
import useGetMessages from '../api/message/hooks/get-messages-hook'

interface ChatWindowProps {
  chat_id: string | undefined
}

export default function ChatWindow(props: ChatWindowProps) {
  const { chat_id } = props
  const chatWindowRef = useRef<HTMLDivElement>(null)
  const { getChatMessages } = useGetMessages()
  const messages = useMessagesStore((state) => state.messages[chat_id ?? ''])
  const messagesList = Object.values(messages ?? {})

  // Automatically fetch the chat messages when the chat_id changes
  useEffect(() => {
    if (!chat_id) return

    getChatMessages(chat_id)
  }, [chat_id])

  // Reverse the messages list to show the newest at the bottom
  const reversedList = [...messagesList].reverse()

  return (
    <div ref={chatWindowRef} className="grow overflow-y-scroll bg-zinc-900 flex flex-col-reverse gap-y-5">
      <div className={'h-1'}></div>
      {reversedList.map((message) => {
        const isSender = message.contact_id === null

        if (isSender) {
          return <ChatSendBubble key={message.id} message={message} />
        } else {
          return <ChatReceiveBubble key={message.id} />
        }
      })}
      <div className={'h-1'}></div>
    </div>
  )
}

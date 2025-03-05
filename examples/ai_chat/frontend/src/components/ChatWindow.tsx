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
  const { getChatMessages, getNewerMessages } = useGetMessages()
  const messages = useMessagesStore((state) => state.messages[chat_id ?? ''])
  const messagesList = Object.values(messages ?? {})
  const pollingInterval = 5000 // 5 seconds
  const pollingRef = useRef<number | null>(null)

  // Function to clear the polling interval
  const clearPolling = () => {
    if (pollingRef.current !== null) {
      clearInterval(pollingRef.current)
      pollingRef.current = null
    }
  }

  // Function to start polling
  const startPolling = (chatId: string) => {
    clearPolling() // Clear any existing interval

    pollingRef.current = setInterval(async () => {
      // only fetch if there are messages to check against.
      if (messagesList.length > 0) {
        const lastMessage = messagesList.reduce((prev, current) =>
          prev.created_at > current.created_at ? prev : current
        )

        if (lastMessage) {
          await getNewerMessages(chatId, lastMessage.id)
        }
      }
    }, pollingInterval) as unknown as number // Type assertion for setInterval return value
  }

  // Automatically fetch the chat messages when the chat_id changes
  // If there are no messages
  useEffect(() => {
    if (!chat_id) return
    if (messagesList.length > 0) {
      // Already have messages, just poll
      startPolling(chat_id)
    }

    getChatMessages(chat_id).then(() => {
      startPolling(chat_id)
    })
  }, [chat_id])

  // Cleanup function to clear the interval when the component unmounts or chat_id changes
  useEffect(() => {
    return () => clearPolling()
  }, [])

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
          return <ChatReceiveBubble key={message.id} message={message} />
        }
      })}
      <div className={'h-1'}></div>
    </div>
  )
}

import { useEffect, useRef } from 'react'
import { useMessagesStore } from '../api/message/store'
import ChatReceiveBubble from './bubbles/ChatReceiveBubble'
import ChatReceiveImageBubble from './bubbles/ChatReceiveImageBubble'
import ChatSendBubble from './bubbles/ChatSendBubble'
import useGetMessages from '../api/message/hooks/get-messages-hook'
import { useChatReadStateStore } from '../api/chat/read-store'

interface ChatWindowProps {
  chat_id: string | undefined
}

export default function ChatWindow(props: ChatWindowProps) {
  const { chat_id } = props
  const chatWindowRef = useRef<HTMLDivElement>(null)
  const { getChatMessages, pollForNewerMessages } = useGetMessages()
  const markChatRead = useChatReadStateStore((state) => state.markChatRead)
  const messages = useMessagesStore((state) => state.messages[chat_id ?? ''])
  const messagesList = Object.values(messages ?? {})
  const sortedMessagesList = [...messagesList].sort((a, b) => a.created_at.getTime() - b.created_at.getTime())

  // Latest message
  const latestMessageId = sortedMessagesList[sortedMessagesList.length - 1]?.id ?? null

  // Automatically fetch initial round of messages if there are none
  useEffect(() => {
    if (!chat_id) return
    getChatMessages(chat_id)
  }, [chat_id])

  // If there are messages, activate the poll
  useEffect(() => {
    if (!chat_id) return
    if (!latestMessageId) return

    if (sortedMessagesList.length > 0) {
      pollForNewerMessages(chat_id, latestMessageId)
    }
  }, [latestMessageId])

  // While viewing a chat, treat any incoming messages as read
  useEffect(() => {
    if (!chat_id) return
    if (sortedMessagesList.length === 0) return
    const latestReadAt = sortedMessagesList[sortedMessagesList.length - 1].created_at.getTime()
    markChatRead(chat_id, latestReadAt)
  }, [chat_id, latestMessageId, sortedMessagesList.length, markChatRead])

  // Reverse the messages list to show the newest at the bottom
  const reversedList = [...sortedMessagesList].reverse()

  return (
    <div ref={chatWindowRef} className="grow overflow-y-scroll bg-zinc-900 flex flex-col-reverse gap-y-5">
      <div className={'h-1'}></div>
      {reversedList.map((message) => {
        const isSender = message.contact_id === null

        if (isSender) {
          return <ChatSendBubble key={message.id} message={message} />
        } else {
          if (message.image_id) {
            return <ChatReceiveImageBubble key={message.id} message={message} />
          } else {
            return <ChatReceiveBubble key={message.id} message={message} />
          }
        }
      })}
      <div className={'h-1'}></div>
    </div>
  )
}

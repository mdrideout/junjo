import { useEffect, useRef, useState } from 'react'
import { useMessagesStore } from '../api/message/store'
import ChatReceiveBubble from './bubbles/ChatReceiveBubble'
import ChatSendBubble from './bubbles/ChatSendBubble'

interface ChatWindowProps {
  chat_id: string | undefined
}

export default function ChatWindow(props: ChatWindowProps) {
  const { chat_id } = props
  const chatWindowRef = useRef<HTMLDivElement>(null)
  const messages = useMessagesStore((state) => state.messages[chat_id ?? ''])
  const messagesList = Object.values(messages ?? {})

  // Local state
  const [atBottom, setAtBottom] = useState(true)

  // At Bottom Check
  useEffect(() => {
    const chatWindow = chatWindowRef.current
    if (!chatWindow) return

    const checkScrollPosition = () => {
      const isAtBottom = chatWindow.scrollHeight - chatWindow.scrollTop <= chatWindow.clientHeight + 1 //Added +1 for tolerance
      setAtBottom(isAtBottom)
    }

    // Check on initial render and whenever messages change
    checkScrollPosition()

    const handleScroll = () => {
      checkScrollPosition()
    }

    chatWindow.addEventListener('scroll', handleScroll)
    return () => {
      chatWindow.removeEventListener('scroll', handleScroll)
    }
  }, [messagesList])

  // Auto-Scroll If At Bottom
  useEffect(() => {
    const chatWindow = chatWindowRef.current
    if (!chatWindow) return

    if (atBottom) {
      chatWindow.scrollTo({
        top: chatWindow.scrollHeight,
        behavior: 'smooth',
      })
    }
  }, [messagesList, atBottom])

  return (
    <div className="grow overflow-hidden bg-zinc-900 flex flex-col justify-end">
      <div ref={chatWindowRef} className={'grow overflow-y-scroll'}>
        <div className={'h-1'}></div>
        {messagesList.map((message) => {
          const isSender = message.contact_id === null

          if (isSender) {
            return <ChatSendBubble message={message} />
          } else {
            return <ChatReceiveBubble />
          }
        })}
        <div className={'h-1'}></div>
      </div>
    </div>
  )
}

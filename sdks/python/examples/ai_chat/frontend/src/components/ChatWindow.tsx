import { useEffect, useMemo, useRef } from 'react'
import type { PublicConfig, Turn } from '../api/schemas'
import ChatReceiveBubble from './bubbles/ChatReceiveBubble'
import ChatReceiveImageBubble from './bubbles/ChatReceiveImageBubble'
import ChatSendBubble from './bubbles/ChatSendBubble'

interface ChatWindowProps {
  chatId: string | undefined
  turns: Turn[]
  config: PublicConfig | null
  loading: boolean
}

export default function ChatWindow({ chatId, turns, config, loading }: ChatWindowProps) {
  const ref = useRef<HTMLDivElement>(null)
  const messages = useMemo(() => turns.flatMap((turn) => [
    { message: turn.user_message, turn },
    ...(turn.assistant_message === null ? [] : [{ message: turn.assistant_message, turn }]),
  ]).sort((left, right) => Date.parse(left.message.created_at) - Date.parse(right.message.created_at)), [turns])

  useEffect(() => {
    ref.current?.scrollTo({ top: ref.current.scrollHeight })
  }, [messages.length])

  if (chatId === undefined) {
    return <div className="grow bg-zinc-900 grid place-items-center text-zinc-500">Select or create a chat.</div>
  }
  if (loading && messages.length === 0) {
    return <div className="grow bg-zinc-900 grid place-items-center text-zinc-500">Loading...</div>
  }

  return (
    <div ref={ref} className="grow overflow-y-scroll bg-zinc-900 flex flex-col gap-y-5 py-1">
      {messages.map(({ message, turn }) => {
        if (message.role === 'user') {
          return <ChatSendBubble key={message.id} message={message} />
        }
        if (message.image_url !== null) {
          return <ChatReceiveImageBubble key={message.id} message={message} turn={turn} config={config} />
        }
        return <ChatReceiveBubble key={message.id} message={message} turn={turn} config={config} />
      })}
    </div>
  )
}

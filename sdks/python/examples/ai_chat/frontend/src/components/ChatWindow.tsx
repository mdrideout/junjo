import { useEffect, useMemo, useRef } from 'react'
import type { Message, PublicConfig, Turn } from '../api/schemas'
import ChatReceiveFailureBubble from './bubbles/ChatReceiveFailureBubble'
import ChatReceiveBubble from './bubbles/ChatReceiveBubble'
import ChatReceiveImageBubble from './bubbles/ChatReceiveImageBubble'
import ChatSendBubble from './bubbles/ChatSendBubble'

interface ChatWindowProps {
  chatId: string | undefined
  turns: Turn[]
  config: PublicConfig | null
  loading: boolean
}

type ChatItem =
  | { kind: 'message'; message: Message; turn: Turn; createdAt: string }
  | { kind: 'failure'; turn: Turn; createdAt: string }

export default function ChatWindow({ chatId, turns, config, loading }: ChatWindowProps) {
  const ref = useRef<HTMLDivElement>(null)
  const items = useMemo(() => turns.flatMap<ChatItem>((turn) => {
    const turnItems: ChatItem[] = [
      { kind: 'message', message: turn.user_message, turn, createdAt: turn.user_message.created_at },
    ]
    if (turn.assistant_message !== null) {
      turnItems.push({
        kind: 'message',
        message: turn.assistant_message,
        turn,
        createdAt: turn.assistant_message.created_at,
      })
    } else if (turn.failure !== null) {
      turnItems.push({
        kind: 'failure',
        turn,
        createdAt: turn.completed_at ?? turn.updated_at,
      })
    }
    return turnItems
  }).sort((left, right) => Date.parse(left.createdAt) - Date.parse(right.createdAt)), [turns])

  useEffect(() => {
    ref.current?.scrollTo({ top: ref.current.scrollHeight })
  }, [items.length])

  if (chatId === undefined) {
    return <div className="grow bg-zinc-900 grid place-items-center text-zinc-500">Select or create a chat.</div>
  }
  if (loading && items.length === 0) {
    return <div className="grow bg-zinc-900 grid place-items-center text-zinc-500">Loading...</div>
  }

  return (
    <div ref={ref} className="grow overflow-y-scroll bg-zinc-900 flex flex-col gap-y-5 py-1">
      {items.map((item) => {
        if (item.kind === 'failure') {
          return <ChatReceiveFailureBubble key={`${item.turn.id}-failure`} turn={item.turn} config={config} />
        }
        const { message, turn } = item
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

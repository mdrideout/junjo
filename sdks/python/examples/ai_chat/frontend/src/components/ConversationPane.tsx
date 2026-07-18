import { useEffect, useMemo } from 'react'
import type { PublicConfig } from '../api/schemas'
import { useConversationTurns } from '../hooks/useConversationTurns'
import ChatForm from './ChatForm'
import ChatWindow from './ChatWindow'

interface ConversationPaneProps {
  conversationId: string
  config: PublicConfig | null
  onViewed: (conversationId: string, latestMessageAt: number) => void
}

export default function ConversationPane({
  conversationId,
  config,
  onViewed,
}: ConversationPaneProps) {
  const conversation = useConversationTurns(conversationId)
  const latestMessageAt = useMemo(() => {
    const latest = conversation.turns[conversation.turns.length - 1]
    return latest === undefined ? null : Date.parse(latest.updated_at)
  }, [conversation.turns])

  useEffect(() => {
    if (latestMessageAt !== null) onViewed(conversationId, latestMessageAt)
  }, [conversationId, latestMessageAt, onViewed])

  return (
    <>
      {conversation.error !== null && (
        <div className="bg-red-950 text-red-100 px-4 py-2 text-sm" role="alert">
          {conversation.error.message}
        </div>
      )}
      <ChatWindow
        chatId={conversationId}
        turns={conversation.turns}
        config={config}
        loading={conversation.loading}
      />
      <ChatForm
        chatId={conversationId}
        sending={conversation.sending}
        onSubmit={conversation.sendTurn}
      />
    </>
  )
}

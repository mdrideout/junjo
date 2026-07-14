import { useEffect, useMemo, useState } from 'react'
import { useNavigate, useParams } from 'react-router'
import ChatForm from './components/ChatForm'
import ChatHeader from './components/ChatHeader'
import ChatSidebar from './components/sidebar/ChatSidebar'
import ChatWindow from './components/ChatWindow'
import { useChat } from './hooks/useChat'

export default function App() {
  const { chat_id: chatId } = useParams()
  const navigate = useNavigate()
  const chat = useChat(chatId)
  const [lastReadAtByChatId, setLastReadAtByChatId] = useState<Record<string, number>>({})

  useEffect(() => {
    if (chatId === undefined && chat.selectedConversationId !== null) {
      navigate(`/${chat.selectedConversationId}`, { replace: true })
    }
  }, [chat.selectedConversationId, chatId, navigate])

  const latestMessageAt = useMemo(() => {
    const latest = chat.turns[chat.turns.length - 1]
    return latest === undefined ? null : Date.parse(latest.updated_at)
  }, [chat.turns])

  useEffect(() => {
    if (chatId === undefined || latestMessageAt === null) return
    setLastReadAtByChatId((current) => ({ ...current, [chatId]: latestMessageAt }))
  }, [chatId, latestMessageAt])

  const selectConversation = (conversationId: string) => {
    chat.selectConversation(conversationId)
    navigate(`/${conversationId}`)
  }

  const createContact = async (sex: 'male' | 'female') => {
    const conversation = await chat.createContact(sex)
    if (conversation !== null) navigate(`/${conversation.id}`)
  }

  return (
    <div className="h-dvh w-dvw p-5">
      <div className="w-full h-full max-w-5xl flex gap-x-5 m-auto">
        <div className="bg-zinc-700 rounded-3xl p-3 overflow-y-scroll w-xs min-w-2xs">
          <ChatSidebar
            conversations={chat.conversations}
            activeChatId={chatId}
            loading={chat.loadingConversations}
            creatingContact={chat.creatingContact}
            lastReadAtByChatId={lastReadAtByChatId}
            onSelect={selectConversation}
            onCreateContact={createContact}
          />
        </div>
        <div className="bg-zinc-700 rounded-3xl grow flex flex-col border-l border-r border-zinc-700 min-w-0">
          <ChatHeader title={chat.conversations.find((item) => item.id === chatId)?.title} />
          {chat.error !== null && (
            <div className="bg-red-950 text-red-100 px-4 py-2 text-sm" role="alert">
              {chat.error.message}
            </div>
          )}
          <ChatWindow
            chatId={chatId}
            turns={chat.turns}
            config={chat.config}
            loading={chat.loadingTurns}
          />
          <ChatForm chatId={chatId} sending={chat.sending} onSubmit={chat.sendTurn} />
        </div>
      </div>
    </div>
  )
}

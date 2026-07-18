import { useCallback, useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router'
import ChatForm from './components/ChatForm'
import ChatHeader from './components/ChatHeader'
import ConversationPane from './components/ConversationPane'
import ChatSidebar from './components/sidebar/ChatSidebar'
import ChatWindow from './components/ChatWindow'
import { useChatShell } from './hooks/useChatShell'

function EmptyConversation() {
  return (
    <>
      <ChatWindow chatId={undefined} turns={[]} config={null} loading={false} />
      <ChatForm chatId={undefined} sending={false} onSubmit={async () => false} />
    </>
  )
}

export default function App() {
  const { chat_id: chatId } = useParams()
  const navigate = useNavigate()
  const shell = useChatShell()
  const [lastReadAtByChatId, setLastReadAtByChatId] = useState<Record<string, number>>(() => {
    try {
      const stored = window.localStorage.getItem('ai-chat:last-read-at')
      if (stored === null) return {}
      const parsed: unknown = JSON.parse(stored)
      if (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed)) return {}
      return Object.fromEntries(
        Object.entries(parsed).filter((entry): entry is [string, number] => typeof entry[1] === 'number'),
      )
    } catch {
      return {}
    }
  })

  useEffect(() => {
    window.localStorage.setItem('ai-chat:last-read-at', JSON.stringify(lastReadAtByChatId))
  }, [lastReadAtByChatId])

  useEffect(() => {
    const firstConversationId = shell.conversations[0]?.id
    if (chatId === undefined && firstConversationId !== undefined) {
      navigate(`/${firstConversationId}`, { replace: true })
    }
  }, [chatId, navigate, shell.conversations])

  const markConversationViewed = useCallback((conversationId: string, latestMessageAt: number) => {
    setLastReadAtByChatId((current) => {
      if ((current[conversationId] ?? 0) >= latestMessageAt) return current
      return { ...current, [conversationId]: latestMessageAt }
    })
  }, [])

  const selectConversation = (conversationId: string) => {
    navigate(`/${conversationId}`)
  }

  const createContact = async (sex: 'male' | 'female') => {
    const conversation = await shell.createContact(sex)
    if (conversation !== null) navigate(`/${conversation.id}`)
  }

  const selectedConversation = shell.conversations.find((item) => item.id === chatId)

  return (
    <div className="h-dvh w-dvw p-5">
      <div className="w-full h-full max-w-5xl flex gap-x-5 m-auto">
        <div className="bg-zinc-700 rounded-3xl p-3 overflow-y-scroll w-xs min-w-2xs">
          <ChatSidebar
            conversations={shell.conversations}
            activeChatId={chatId}
            loading={shell.loading}
            creatingContact={shell.creatingContact}
            lastReadAtByChatId={lastReadAtByChatId}
            onSelect={selectConversation}
            onCreateContact={createContact}
          />
        </div>
        <div className="bg-zinc-700 rounded-3xl grow flex flex-col border-l border-r border-zinc-700 min-w-0">
          <ChatHeader title={selectedConversation?.title} />
          {shell.error !== null && (
            <div className="bg-red-950 text-red-100 px-4 py-2 text-sm" role="alert">
              {shell.error.message}
            </div>
          )}
          {chatId === undefined ? (
            <EmptyConversation />
          ) : (
            <ConversationPane
              key={chatId}
              conversationId={chatId}
              config={shell.config}
              onViewed={markConversationViewed}
            />
          )}
        </div>
      </div>
    </div>
  )
}

import ChatForm from './components/ChatForm'
import ChatHeader from './components/ChatHeader'
import ChatSidebar from './components/sidebar/ChatSidebar'
import ChatWindow from './components/ChatWindow'
import { useParams } from 'react-router'
import { useEffect } from 'react'
import { useChatReadStateStore } from './api/chat/read-store'

function App() {
  const { chat_id } = useParams()
  const markChatRead = useChatReadStateStore((state) => state.markChatRead)

  useEffect(() => {
    if (!chat_id) return
    markChatRead(chat_id)
  }, [chat_id, markChatRead])

  return (
    <div className={'h-dvh w-dvw p-5'}>
      <div className={'w-full h-full max-w-5xl flex gap-x-5 m-auto'}>
        <div className="bg-zinc-700 rounded-3xl p-3 overflow-y-scroll w-xs min-w-2xs">
          <ChatSidebar />
        </div>
        <div className="bg-zinc-700 rounded-3xl grow flex flex-col border-l border-r border-zinc-700">
          <ChatHeader chat_id={chat_id} />
          <ChatWindow chat_id={chat_id} />
          <ChatForm chat_id={chat_id} />
        </div>
      </div>
    </div>
  )
}

export default App

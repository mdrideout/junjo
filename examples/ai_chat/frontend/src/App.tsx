import ChatForm from './components/ChatForm'
import ChatHeader from './components/ChatHeader'
import ChatSidebar from './components/sidebar/ChatSidebar'
import ChatWindow from './components/ChatWindow'
import { useParams } from 'react-router'

function App() {
  const { chat_id } = useParams()

  return (
    <div className={'h-dvh w-dvw p-5'}>
      <div className={'w-full h-full max-w-5xl flex gap-x-5 m-auto'}>
        <div className="bg-zinc-700 rounded-3xl p-5 overflow-y-scroll w-xs min-w-2xs">
          <ChatSidebar />
        </div>
        <div className="bg-zinc-700 rounded-3xl grow flex flex-col border-l border-r border-zinc-700">
          <ChatHeader chat_id={chat_id} />
          <ChatWindow />
          <ChatForm />
        </div>
      </div>
    </div>
  )
}

export default App

import { useState } from 'react'
import ChatForm from './components/ChatForm'
import ChatHeader from './components/ChatHeader'

function App() {
  const [count, setCount] = useState(0)

  return (
    <div className={'h-dvh w-dvw p-5'}>
      <div className={'w-full h-full flex gap-x-5'}>
        <div className="bg-zinc-700 rounded-3xl p-5 overflow-y-scroll w-xs">
          <button className="w-full border border-blue-300 rounded-md bg-blue-600 text-white leading-none px-3 py-1 mb-4">
            New Chat
          </button>
          <div>
            Chat Item Here
            <br />
            Chat Item Here
            <br />
            Chat Item Here
            <br />
            Chat Item Here
            <br />
            Chat Item Here
            <br />
            Chat Item Here
            <br />
          </div>
        </div>
        <div className="bg-zinc-700 rounded-3xl grow flex flex-col border-l border-r border-zinc-700">
          <ChatHeader />
          <div className="grow overflow-y-scroll bg-zinc-900 px-5">Chat Window</div>
          <ChatForm />
        </div>
      </div>
    </div>
  )
}

export default App

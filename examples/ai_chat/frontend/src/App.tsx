import { useState } from 'react'
import ChatForm from './components/ChatForm'
import ChatHeader from './components/ChatHeader'
import ChatWindow from './components/ChatWindow'

function App() {
  const [count, setCount] = useState(0)

  return (
    <div className={'h-dvh w-dvw p-5'}>
      <div className={'w-full h-full max-w-5xl flex gap-x-5 m-auto'}>
        <div className="bg-zinc-700 rounded-3xl p-5 overflow-y-scroll w-xs min-w-2xs">
          <button className="w-full cursor-pointer border border-blue-300 rounded-md bg-gradient-to-b from-blue-600 to-blue-700 hover:to-blue-800 text-white leading-none px-3 py-1 mb-4">
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
          <ChatWindow />
          <ChatForm />
        </div>
      </div>
    </div>
  )
}

export default App

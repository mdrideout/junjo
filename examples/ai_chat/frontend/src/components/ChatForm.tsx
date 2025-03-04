import { useState } from 'react'
import useSendMessage from '../api/message/hook'

export interface ChatFormProps {
  chat_id: string | undefined
}

export default function ChatForm(props: ChatFormProps) {
  const { chat_id } = props
  const [message, setMessage] = useState('')
  const { isLoading, error, sendMessage } = useSendMessage()

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!message.trim() || !chat_id) return // Prevent sending empty messages

    try {
      await sendMessage({ chat_id, message })
      setMessage('') // Clear the input field after sending
    } catch (err: any) {
      console.error('Error sending message:', err)
      // Handle the error appropriately, e.g., display an error message to the user.
      alert('Error sending message: ' + err.message)
    }
  }

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      if (message.trim() && chat_id) {
        handleSubmit(e as any)
      }
    }
  }

  return (
    <div>
      {error && <div className={'text-red-500 text-sm font-bold px-4 pt-2'}>{error}</div>}
      {chat_id && (
        <form onSubmit={handleSubmit} className="p-4 grid grid-cols-[auto_100px] gap-x-2 items-end">
          <div>
            <textarea
              value={message}
              onChange={(e) => setMessage(e.target.value)}
              onKeyDown={handleKeyDown}
              className={
                'w-full rounded-md bg-zinc-300 text-zinc-800 px-3 py-3 leading-tight border-0 ring-0 outline-0'
              }
              rows={3}
              placeholder="Send a chat..."
            />
          </div>
          <div className="h-full pb-1.5">
            <button
              type="submit"
              disabled={isLoading}
              className={`w-full h-full cursor-pointer border border-blue-300 rounded-md bg-gradient-to-b from-blue-600 to-blue-700 hover:to-blue-800 text-white leading-none px-3 py-1 ${
                isLoading ? 'opacity-50' : ''
              }`}
            >
              {isLoading ? '...' : 'Send'}
            </button>
          </div>
        </form>
      )}
    </div>
  )
}

import { useState } from 'react'

interface ChatFormProps {
  chatId: string | undefined
  sending: boolean
  onSubmit: (message: string) => Promise<boolean>
}

export default function ChatForm({ chatId, sending, onSubmit }: ChatFormProps) {
  const [message, setMessage] = useState('')

  const submit = async (event: React.FormEvent) => {
    event.preventDefault()
    if (chatId === undefined || !message.trim() || sending) return
    if (await onSubmit(message)) setMessage('')
  }

  return (
    <form onSubmit={submit} className="p-4 grid grid-cols-[auto_100px] gap-x-2 items-end">
      {chatId !== undefined && (
        <>
          <textarea
            value={message}
            onChange={(event) => setMessage(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter' && !event.shiftKey) {
                event.preventDefault()
                event.currentTarget.form?.requestSubmit()
              }
            }}
            className="w-full rounded-md bg-zinc-300 text-zinc-800 px-3 py-3 leading-tight border-0 ring-0 outline-0"
            rows={3}
            maxLength={2500}
            placeholder="Send a chat..."
            aria-label="Message"
          />
          <div className="h-full pb-1.5">
            <button
              type="submit"
              disabled={sending || !message.trim()}
              className="w-full h-full cursor-pointer border border-blue-300 rounded-md bg-gradient-to-b from-blue-600 to-blue-700 hover:to-blue-800 text-white leading-none px-3 py-1 disabled:opacity-50"
            >
              {sending ? '...' : 'Send'}
            </button>
          </div>
        </>
      )}
    </form>
  )
}

import { useState } from 'react'
import { formatDateForChat } from '../../util/date-utils'
import FullscreenImageModal from '../modals/FullscreenImageModal'
import { ChatBubbleProps } from './schemas'

export default function ChatReceiveImageBubble(props: ChatBubbleProps) {
  const { message } = props
  const [isFullScreen, setIsFullScreen] = useState(false)

  if (!message.image_id) {
    return null
  }

  const lastMessageTime = new Date(message.created_at)
  const dateString = formatDateForChat(lastMessageTime)
  const imageUrl = `http://127.0.0.1:8000/api/chat-image/${message.chat_id}/${message.image_id}`

  return (
    <div className="w-full flex justify-start">
      <div className="pr-[15%] pl-5 relative">
        <div className="rounded-2xl bg-gradient-to-bl from-zinc-500 to-zinc-600 text-zinc-100 leading-tight relative">
          <div className="absolute left-[-9px] bottom-3 w-0 h-0 border-t-[10px] border-t-transparent border-r-[10px] border-r-zinc-600 border-b-[10px] border-b-transparent"></div>
          <img
            src={imageUrl}
            alt="chat content"
            className={`cursor-zoom-in rounded-t-2xl ${message.message ? '' : 'rounded-b-2xl'}`}
            onClick={() => setIsFullScreen(true)}
          />
          {message.message && <div className="safe-word-break px-4 py-3 leading-tight">{message.message}</div>}
        </div>
        <div className={'text-[10px] text-zinc-400 text-left pl-2 mt-[1px]'}>{dateString}</div>
      </div>
      {isFullScreen && (
        <FullscreenImageModal src={imageUrl} alt="chat content" onClose={() => setIsFullScreen(false)} />
      )}
    </div>
  )
}

import { formatDateForChat } from '../../util/date-utils'
import { ChatBubbleProps } from './schemas'

export default function ChatReceiveBubble(props: ChatBubbleProps) {
  const { message } = props

  const lastMessageTime = new Date(message.created_at)
  const dateString = formatDateForChat(lastMessageTime)

  return (
    <div className="w-full flex justify-start">
      <div className="pr-[15%] pl-5 relative">
        <div className="safe-word-break px-4 py-3 rounded-2xl bg-gradient-to-bl from-zinc-500 to-zinc-600 text-zinc-100 leading-tight relative">
          <div className="absolute left-[-9px] bottom-3 w-0 h-0 border-t-[10px] border-t-transparent border-r-[10px] border-r-zinc-600 border-b-[10px] border-b-transparent"></div>
          {message.message}
        </div>
        <div className={'text-[10px] text-zinc-400 text-left pl-2 mt-[1px]'}>{dateString}</div>
      </div>
    </div>
  )
}

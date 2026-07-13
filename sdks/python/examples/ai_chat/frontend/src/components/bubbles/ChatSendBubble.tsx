import { formatDateForChat } from '../../util/date-utils'
import { ChatBubbleProps } from './schemas'

export default function ChatSendBubble(props: ChatBubbleProps) {
  const { message } = props

  const lastMessageTime = new Date(message.created_at)
  const dateString = formatDateForChat(lastMessageTime)

  return (
    <div className="w-full flex justify-end">
      <div className={'pl-[15%] max-w-xl pr-5'}>
        <div className="safe-word-break px-4 py-3 rounded-2xl bg-gradient-to-br from-blue-600 to-blue-700 text-blue-100 leading-tight relative">
          <div className="absolute right-[-9px] bottom-3 w-0 h-0 border-t-[10px] border-t-transparent border-l-[10px] border-l-blue-700 border-b-[10px] border-b-transparent"></div>
          {message.message}
        </div>
        <div className={'text-[10px] text-zinc-400 text-right pr-2 mt-[1px]'}>{dateString}</div>
      </div>
    </div>
  )
}

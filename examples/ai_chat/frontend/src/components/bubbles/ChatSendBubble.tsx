import { ChatBubbleProps } from './schemas'

export default function ChatSendBubble(props: ChatBubbleProps) {
  const { message } = props
  return (
    <div className="w-full my-5 flex justify-end">
      <div className={'grow pl-[15%] max-w-xl pr-5 relative'}>
        <div className="safe-word-break bg-gradient-to-b from-blue-600 to-blue-700 text-blue-100 rounded-3xl leading-tight px-6 py-5 relative">
          <div className="absolute right-[-9px] bottom-5.5 w-0 h-0 border-t-[10px] border-t-transparent border-l-[10px] border-l-blue-600 border-b-[10px] border-b-transparent"></div>
          {message.message}
        </div>
      </div>
    </div>
  )
}

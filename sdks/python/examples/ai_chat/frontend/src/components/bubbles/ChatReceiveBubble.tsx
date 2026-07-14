import { formatDateForChat } from '../../util/date-utils'
import { TurnDiagnostics } from '../TurnDiagnostics'
import type { ChatBubbleProps } from './schemas'

export default function ChatReceiveBubble({ message, turn, config }: ChatBubbleProps) {
  return (
    <div className="w-full flex justify-start">
      <div className="pr-[15%] pl-5 relative max-w-xl">
        <div className="safe-word-break px-4 py-3 rounded-2xl bg-gradient-to-bl from-zinc-500 to-zinc-600 text-zinc-100 leading-tight relative">
          <div className="absolute left-[-9px] bottom-3 w-0 h-0 border-t-[10px] border-t-transparent border-r-[10px] border-r-zinc-600 border-b-[10px] border-b-transparent" />
          {message.content}
          {config?.debug_enabled === true && turn !== undefined && (
            <TurnDiagnostics turn={turn} config={config} />
          )}
        </div>
        <div className="text-[10px] text-zinc-400 text-left pl-2 mt-px">
          {formatDateForChat(new Date(message.created_at))}
        </div>
      </div>
    </div>
  )
}

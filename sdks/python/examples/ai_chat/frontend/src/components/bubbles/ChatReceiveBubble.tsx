import { formatDateForChat } from '../../util/date-utils'
import { TurnDiagnostics } from '../TurnDiagnostics'
import type { ChatBubbleProps } from './schemas'

export default function ChatReceiveBubble({ message, turn, config }: ChatBubbleProps) {
  const failed = turn?.failure !== null && turn?.failure !== undefined
  return (
    <div className="w-full flex justify-start">
      <div className="pr-[15%] pl-5 relative max-w-xl">
        <div className={`safe-word-break px-4 py-3 rounded-2xl bg-gradient-to-bl text-zinc-100 leading-tight relative ${failed ? 'from-red-800 to-red-950 ring-1 ring-red-500/40' : 'from-zinc-500 to-zinc-600'}`}>
          <div className={`absolute left-[-9px] bottom-3 w-0 h-0 border-t-[10px] border-t-transparent border-r-[10px] border-b-[10px] border-b-transparent ${failed ? 'border-r-red-950' : 'border-r-zinc-600'}`} />
          {message.content}
          {turn !== undefined && (failed || config?.studio_frontend_base_url != null) && (
            <TurnDiagnostics turn={turn} config={config ?? null} />
          )}
        </div>
        <div className="text-[10px] text-zinc-400 text-left pl-2 mt-px">
          {formatDateForChat(new Date(message.created_at))}
        </div>
      </div>
    </div>
  )
}

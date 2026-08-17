import type { PublicConfig, Turn } from '../../api/schemas'
import { formatDateForChat } from '../../util/date-utils'
import { TurnDiagnostics } from '../TurnDiagnostics'

interface ChatReceiveFailureBubbleProps {
  turn: Turn
  config: PublicConfig | null
}

export default function ChatReceiveFailureBubble({ turn, config }: ChatReceiveFailureBubbleProps) {
  if (turn.failure === null) return null

  return (
    <div className="w-full flex justify-start">
      <div className="pr-[15%] pl-5 relative max-w-xl">
        <div
          className="safe-word-break px-4 py-3 rounded-2xl bg-gradient-to-bl from-red-800 to-red-950 text-red-50 leading-tight relative ring-1 ring-red-500/40"
          role="alert"
        >
          <div className="absolute left-[-9px] bottom-3 w-0 h-0 border-t-[10px] border-t-transparent border-r-[10px] border-r-red-950 border-b-[10px] border-b-transparent" />
          <div className="font-semibold">{turn.failure.detail}</div>
          <div className="mt-1 text-xs text-red-200">
            Failure code: <code>{turn.failure.code}</code>
          </div>
          <TurnDiagnostics turn={turn} config={config} />
        </div>
        <div className="text-[10px] text-red-300 text-left pl-2 mt-px">
          {formatDateForChat(new Date(turn.completed_at ?? turn.updated_at))}
        </div>
      </div>
    </div>
  )
}

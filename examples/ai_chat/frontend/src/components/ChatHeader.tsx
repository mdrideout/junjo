export interface ChatHeaderProps {
  chat_id: string | undefined
}

export default function ChatHeader(props: ChatHeaderProps) {
  const { chat_id } = props

  const title = chat_id ?? 'No chat selected'

  return (
    <div className="rounded-t-3xl p-2 text-sm font-bold bg-zinc-700 text-zinc-100 flex justify-center">{title}</div>
  )
}

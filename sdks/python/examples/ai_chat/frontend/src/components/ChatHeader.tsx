interface ChatHeaderProps {
  title: string | undefined
}

export default function ChatHeader({ title }: ChatHeaderProps) {
  return (
    <div className="rounded-t-3xl p-2 text-sm font-bold bg-zinc-700 text-zinc-100 flex justify-center">
      {title ?? 'No chat selected'}
    </div>
  )
}

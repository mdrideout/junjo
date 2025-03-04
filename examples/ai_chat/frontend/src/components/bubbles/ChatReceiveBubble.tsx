export default function ChatReceiveBubble() {
  return (
    <div className="w-full pr-[10%] pl-2 relative">
      <div className="safe-word-break bg-gradient-to-b from-zinc-200 to-zinc-300 text-zinc-800 rounded-3xl leading-tight px-6 py-5 relative">
        <div className="absolute left-[-9px] bottom-5.5 w-0 h-0 border-t-[10px] border-t-transparent border-r-[10px] border-r-zinc-300 border-b-[10px] border-b-transparent"></div>
        This is a message that was received from the user in a chat bubble. It is long enough to wrap to multiple lines.
        This is a message that was received from the user in a chat bubble. It is long enough to wrap to multiple lines.
        This is a message that was received from the user in a chat bubble. It is long enough to wrap to multiple lines.
      </div>
    </div>
  )
}

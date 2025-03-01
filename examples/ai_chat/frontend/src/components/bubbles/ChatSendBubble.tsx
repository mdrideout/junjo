export default function ChatSendBubble() {
  return (
    <div className="w-full py-5 pl-[15%] max-w-xl pr-2 relative">
      <div className="bg-gradient-to-b from-blue-600 to-blue-700 text-blue-100 rounded-3xl leading-tight px-6 py-5 relative">
        <div className="absolute right-[-10px] bottom-5.5 w-0 h-0 border-t-[10px] border-t-transparent border-l-[10px] border-l-blue-700 border-b-[10px] border-b-transparent"></div>
        This is a message that was sent by the user in a chat bubble. It is long enough to wrap to multiple lines. This
        is a message that was sent by the user in a chat bubble. It is long enough to wrap to multiple lines. This is a
        message that was sent by the user in a chat bubble. It is long enough to wrap to multiple lines.
      </div>
    </div>
  )
}

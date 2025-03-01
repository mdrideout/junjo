import ChatReceiveBubble from './bubbles/ChatReceiveBubble'
import ChatSendBubble from './bubbles/ChatSendBubble'

export default function ChatWindow() {
  return (
    <div className="grow h-full overflow-y-scroll bg-zinc-900 px-5 flex flex-col items-end">
      <ChatSendBubble />
      <ChatReceiveBubble />
      <ChatSendBubble />
      <ChatReceiveBubble />
      <ChatSendBubble />
      <ChatReceiveBubble />
      <ChatSendBubble />
      <ChatReceiveBubble />
    </div>
  )
}

import type { Conversation } from '../../api/schemas'
import { formatDateForChat } from '../../util/date-utils'
import SidebarAvatar from '../avatars/SidebarAvatar'
import NewContactButton from './NewContactButton'

interface ChatSidebarProps {
  conversations: Conversation[]
  activeChatId: string | undefined
  loading: boolean
  creatingContact: boolean
  lastReadAtByChatId: Record<string, number>
  onSelect: (conversationId: string) => void
  onCreateContact: (sex: 'male' | 'female') => Promise<void>
}

export default function ChatSidebar({
  conversations,
  activeChatId,
  loading,
  creatingContact,
  lastReadAtByChatId,
  onSelect,
  onCreateContact,
}: ChatSidebarProps) {
  return (
    <>
      <div className="mb-6">
        <NewContactButton loading={creatingContact} onCreate={onCreateContact} />
      </div>
      {loading && <div className="opacity-50 text-center">Loading...</div>}
      {!loading && conversations.length === 0 && <div className="opacity-30 text-center">so lonely...</div>}
      <div className="flex flex-col gap-y-5">
        {conversations.map((conversation) => {
          const lastMessageTime = conversation.last_message_at === null
            ? null
            : Date.parse(conversation.last_message_at)
          const hasUnread = activeChatId !== conversation.id
            && lastMessageTime !== null
            && lastMessageTime > (lastReadAtByChatId[conversation.id] ?? 0)
          return (
            <div key={conversation.id} onClick={() => onSelect(conversation.id)}>
              <SidebarAvatar
                contact={conversation.contact}
                lastMessage={lastMessageTime === null ? 'New conversation' : formatDateForChat(new Date(lastMessageTime))}
                isActive={activeChatId === conversation.id}
                hasUnread={hasUnread}
              />
            </div>
          )
        })}
      </div>
    </>
  )
}

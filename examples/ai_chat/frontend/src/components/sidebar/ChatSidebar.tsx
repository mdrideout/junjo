import { GenderEnum } from '../../api/contact/schemas'
import SidebarAvatar from '../avatars/SidebarAvatar'
import NewContactButton from './NewContactButton'
import useGetChatsWithMembers from '../../api/chat/hook'
import { useChatsWithMembersStore } from '../../api/chat/store'
import useGetContacts from '../../api/contact/hooks/get-contacts-hook'
import { Link, useParams } from 'react-router'
import { formatDateForChat } from '../../util/date-utils'

/**
 * Chat Sidebar
 */
export default function ChatSidebar() {
  const { chat_id } = useParams()
  const { error: contactsError, refetch: refetchContacts } = useGetContacts()
  const { error: chatsWithMembersError, refetch: refetchChatsWithMembers } = useGetChatsWithMembers()
  const { chats } = useChatsWithMembersStore()

  async function handleRefetch() {
    await refetchContacts()
    await refetchChatsWithMembers()
  }

  return (
    <>
      <div className={'mb-6'}>
        <NewContactButton gender={GenderEnum.FEMALE} />
        <div className={'h-2'}></div>
        <NewContactButton gender={GenderEnum.MALE} />
      </div>

      {(contactsError || chatsWithMembersError) && (
        <div className={'mb-5'}>
          <div className={'text-red-500 mb-1'}>Error fetching contacts.</div>
          <button
            className={'bg-blue-500 hover:bg-blue-700 text-white rounded-md px-3 py-1 leading-none cursor-pointer'}
            onClick={handleRefetch}
          >
            Retry
          </button>
        </div>
      )}
      {chats.length === 0 && <div className={'opacity-30 text-center'}>so lonely...</div>}
      <div className={'flex flex-col gap-y-5 px-1'}>
        {chats.map((chat) => {
          // Create a human readable date
          const lastMessageTime = new Date(chat.last_message_time)
          const dateString = formatDateForChat(lastMessageTime)
          const isActive = chat.id == chat_id

          return (
            <Link key={chat.id} to={`/${chat.id}`}>
              {chat.members.map((member) => (
                <SidebarAvatar
                  key={chat.id}
                  lastMessage={dateString}
                  contact_id={member.contact_id}
                  isActive={isActive}
                />
              ))}
            </Link>
          )
        })}
      </div>
    </>
  )
}

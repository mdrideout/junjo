import { GenderEnum } from '../../api/contact/schemas'
import SidebarAvatar from '../avatars/SidebarAvatar'
import NewContactButton from './NewContactButton'
import { useSortedContacts } from '../../api/contact/store'

/**
 * Chat Sidebar
 */
export default function ChatSidebar() {
  const sortedContacts = useSortedContacts()

  return (
    <>
      <div className={'mb-6'}>
        <NewContactButton gender={GenderEnum.FEMALE} />
        <div className={'h-2'}></div>
        <NewContactButton gender={GenderEnum.MALE} />
      </div>
      <div className={'flex flex-col gap-y-4 pl-1'}>
        {sortedContacts.map((contact) => (
          <SidebarAvatar key={contact.id} contact={contact} />
        ))}
      </div>
    </>
  )
}

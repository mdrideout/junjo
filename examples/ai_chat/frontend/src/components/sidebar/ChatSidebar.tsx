import { GenderEnum } from '../../api/contact/schemas'
import SidebarAvatar from '../avatars/SidebarAvatar'
import NewContactButton from './NewContactButton'
import { useSortedContacts } from '../../api/contact/store'
import useGetContacts from '../../api/contact/hooks/get-contacts-hook'

/**
 * Chat Sidebar
 */
export default function ChatSidebar() {
  const { error, refetch } = useGetContacts()
  const sortedContacts = useSortedContacts()

  return (
    <>
      <div className={'mb-6'}>
        <NewContactButton gender={GenderEnum.FEMALE} />
        <div className={'h-2'}></div>
        <NewContactButton gender={GenderEnum.MALE} />
      </div>

      {error && (
        <div className={'mb-5'}>
          <div className={'text-red-500 mb-1'}>Error fetching contacts.</div>
          <button
            className={'bg-blue-500 hover:bg-blue-700 text-white rounded-md px-3 py-1 leading-none cursor-pointer'}
            onClick={() => refetch()}
          >
            Retry
          </button>
        </div>
      )}
      {sortedContacts.length == 0 && <div className={'opacity-30 text-center'}>so lonely...</div>}
      <div className={'flex flex-col gap-y-4 pl-1'}>
        {sortedContacts.map((contact) => (
          <SidebarAvatar key={contact.id} contact={contact} />
        ))}
      </div>
    </>
  )
}

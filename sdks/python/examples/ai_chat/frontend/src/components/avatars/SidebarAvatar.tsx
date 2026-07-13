import { useState } from 'react'
import { useContactStore } from '../../api/contact/store'
import AvatarModal from './AvatarModal'

interface SidebarAvatarProps {
  contact_id: string
  lastMessage: string
  isActive: boolean
  hasUnread?: boolean
}

export default function SidebarAvatar(props: SidebarAvatarProps) {
  const { contact_id, lastMessage, isActive, hasUnread } = props
  const [isModalOpen, setIsModalOpen] = useState(false)

  // Get contact from store
  const contact = useContactStore((state) => state.contact[contact_id])
  if (!contact) return null

  const baseClasses = `text-white w-full flex items-center text-left rounded-2xl gap-x-3 transition-all duration-200 cursor-pointer`
  const activeClasses = `bg-zinc-600`

  let buttonClasses = baseClasses
  if (isActive) {
    buttonClasses += ` ${activeClasses}`
  }

  return (
    <>
      <button className={buttonClasses}>
        <div
          className={'rounded-2xl bg-zinc-400 border-2 border-zinc-100 size-24 bg-cover'}
          style={{
            backgroundImage: `url(http://127.0.0.1:8000/api/avatar/${contact.avatar_id})`,
          }}
        ></div>
        <div>
          <div className="font-semibold text-sm leading-none mb-1">
            {contact.first_name} {contact.last_name}
          </div>
          <div className={'text-xs text-zinc-400'}>{lastMessage}</div>
          <div className={'mt-1 text-xs text-green-400 opacity-70 underline'} onClick={() => setIsModalOpen(true)}>
            View Profile
          </div>
        </div>
        {hasUnread && (
          <div
            className="ml-auto mr-3 w-3 h-3 rounded-full bg-red-500"
            aria-label="Unread messages"
            title="Unread messages"
          />
        )}
      </button>
      {isModalOpen && <AvatarModal contact={contact} onClose={() => setIsModalOpen(false)} />}
    </>
  )
}

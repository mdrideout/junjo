import { useState } from 'react'
import { resolveApiAssetUrl } from '../../api/client'
import type { Contact } from '../../api/schemas'
import AvatarModal from './AvatarModal'

interface SidebarAvatarProps {
  contact: Contact
  lastMessage: string
  isActive: boolean
  hasUnread: boolean
}

export default function SidebarAvatar({ contact, lastMessage, isActive, hasUnread }: SidebarAvatarProps) {
  const [modalOpen, setModalOpen] = useState(false)
  return (
    <>
      <button
        className={`text-white w-full flex items-center text-left rounded-2xl gap-x-3 transition-all duration-200 cursor-pointer ${isActive ? 'bg-zinc-600' : ''}`}
      >
        <div
          className="rounded-2xl bg-zinc-400 border-2 border-zinc-100 size-24 bg-cover bg-center shrink-0"
          style={{ backgroundImage: `url(${resolveApiAssetUrl(contact.avatar_url)})` }}
        />
        <div className="min-w-0">
          <div className="font-semibold text-sm leading-none mb-1 truncate">
            {contact.first_name} {contact.last_name}
          </div>
          <div className="text-xs text-zinc-400">{lastMessage}</div>
          <div
            className="mt-1 text-xs text-green-400 opacity-70 underline"
            onClick={(event) => {
              event.preventDefault()
              event.stopPropagation()
              setModalOpen(true)
            }}
          >
            View Profile
          </div>
        </div>
        {hasUnread && <div className="ml-auto mr-3 w-3 h-3 rounded-full bg-red-500" aria-label="Unread messages" />}
      </button>
      {modalOpen && <AvatarModal contact={contact} onClose={() => setModalOpen(false)} />}
    </>
  )
}

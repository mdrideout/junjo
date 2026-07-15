import { resolveApiAssetUrl } from '../../api/client'
import type { Contact } from '../../api/schemas'

interface AvatarModalProps {
  contact: Contact
  onClose: () => void
}

export default function AvatarModal({ contact, onClose }: AvatarModalProps) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/90" onClick={onClose}>
      <div className="p-0 text-white max-w-xl w-full" onClick={(event) => event.stopPropagation()}>
        <div className="text-right">
          <button
            onClick={onClose}
            className="text-zinc-400 hover:text-white text-2xl cursor-pointer"
            aria-label="Close profile"
          >
            &times;
          </button>
        </div>
        <div className="flex flex-col items-center">
          <img
            src={resolveApiAssetUrl(contact.avatar_url)}
            alt={`${contact.first_name} ${contact.last_name}`}
            className="rounded-2xl bg-zinc-400 w-full mb-4"
          />
          <div className="bg-black p-2 text-sm text-zinc-400 text-left w-full">
            <p className="text-2xl font-bold">{contact.first_name} {contact.last_name}</p>
            <p><strong>Age:</strong> {contact.age}</p>
            <p><strong>Location:</strong> {contact.city}, {contact.state}</p>
            <p className="mt-2">{contact.bio}</p>
          </div>
        </div>
      </div>
    </div>
  )
}

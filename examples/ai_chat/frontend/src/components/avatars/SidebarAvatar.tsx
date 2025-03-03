import { ContactRead, GenderEnum } from '../../api/contact/schemas'
import { useContactStore } from '../../api/contact/store'

interface SidebarAvatarProps {
  contact_id: string
}

export default function SidebarAvatar(props: SidebarAvatarProps) {
  const { contact_id } = props

  // Get contact from store
  const contact = useContactStore((state) => state.contact[contact_id])
  if (!contact) return null

  const isMale = contact.gender === GenderEnum.MALE

  const buttonClasses = `flex items-center rounded-full gap-x-2 transition-all duration-200 cursor-pointer ${
    isMale
      ? 'hover:shadow-[0_0_10px_2px_rgb(81,161,252)] hover:bg-blue-500' // Blue glow and background for male
      : 'hover:shadow-[0_0_10px_2px_rgb(244,114,182)] hover:bg-pink-500' // Pink glow and background for female
  }`

  return (
    <button className={buttonClasses}>
      <div className={'rounded-full bg-zinc-400 border border-zinc-100 size-5'}></div>
      <div className="font-semibold text-sm">
        {contact.first_name} {contact.last_name}
      </div>
    </button>
  )
}

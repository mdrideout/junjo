import { GenderEnum } from '../../api/contact/schemas'
import { useContactStore } from '../../api/contact/store'

interface SidebarAvatarProps {
  contact_id: string
  lastMessage: string
  isActive: boolean
}

export default function SidebarAvatar(props: SidebarAvatarProps) {
  const { contact_id, lastMessage, isActive } = props

  // Get contact from store
  const contact = useContactStore((state) => state.contact[contact_id])
  if (!contact) return null

  const isMale = contact.gender === GenderEnum.MALE

  const baseClasses = `text-white w-full flex items-center text-left rounded-full gap-x-2 transition-all duration-200 cursor-pointer`
  const maleClasses = `hover:bg-gradient-to-b hover:from-blue-600 hover:to-blue-800`
  const femaleClasses = `hover:bg-gradient-to-b hover:from-pink-600 hover:to-pink-800`
  const activeMaleClasses = `bg-zinc-600`
  const activeFemaleClasses = `bg-zinc-600`

  let buttonClasses = baseClasses
  if (isMale) {
    buttonClasses += ` ${maleClasses}`
    if (isActive) {
      buttonClasses += ` ${activeMaleClasses}`
    }
  } else {
    buttonClasses += ` ${femaleClasses}`
    if (isActive) {
      buttonClasses += ` ${activeFemaleClasses}`
    }
  }

  return (
    <button className={buttonClasses}>
      <div className={'rounded-full bg-zinc-400 border-2 border-zinc-100 size-12'}></div>
      <div>
        <div className="font-semibold text-sm leading-none">
          {contact.first_name} {contact.last_name}
        </div>
        <div className={'text-xs'}>{lastMessage}</div>
      </div>
    </button>
  )
}

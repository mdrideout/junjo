import { GenderEnum } from '../../api/contact/schemas'
import SidebarAvatar from '../avatars/SidebarAvatar'
import NewContactButton from './NewContactButton'

/**
 * Chat Sidebar
 */
export default function ChatSidebar() {
  return (
    <>
      <div className={'mb-6'}>
        <NewContactButton gender={GenderEnum.FEMALE} />
        <div className={'h-2'}></div>
        <NewContactButton gender={GenderEnum.MALE} />
      </div>
      <div className={'flex flex-col gap-y-4 pl-1'}>
        <SidebarAvatar gender={'female'} />
        <SidebarAvatar gender={'female'} />
        <SidebarAvatar gender={'male'} />
        <SidebarAvatar gender={'male'} />
        <SidebarAvatar gender={'female'} />
        <SidebarAvatar gender={'male'} />
      </div>
    </>
  )
}

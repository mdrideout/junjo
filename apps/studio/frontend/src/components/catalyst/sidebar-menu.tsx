import {
  AvatarIcon,
  DashboardIcon,
  ExitIcon,
  ExternalLinkIcon,
  GitHubLogoIcon,
  HomeIcon,
  RocketIcon,
  RowsIcon,
} from '@radix-ui/react-icons'
import { Link } from './link'
import { Sidebar, SidebarBody, SidebarHeading, SidebarItem, SidebarLabel, SidebarSection } from './sidebar'
import { AuthContext } from '../../auth/auth-context'
import { useContext } from 'react'

export default function SidebarMenu() {
  const { isAuthenticated } = useContext(AuthContext)

  return (
    <Sidebar>
      <SidebarBody>
        <div className="mb-2 flex">
          <Link href="#" aria-label="Home">
            <div className="mb-2">
              <div className="font-logo text-3xl ml-2.5 mb-1.5">junjo-ui</div>
              <div>Simple AI Graph Workflows</div>
            </div>
          </Link>
        </div>
        <SidebarSection>
          <SidebarItem href="/">
            <HomeIcon />
            <SidebarLabel>Home</SidebarLabel>
          </SidebarItem>
          <SidebarItem href="/dashboard">
            <DashboardIcon />
            <SidebarLabel>Dashboard</SidebarLabel>
          </SidebarItem>
          <SidebarItem href="/dashboard/logs">
            <RowsIcon />
            <SidebarLabel>Logs</SidebarLabel>
          </SidebarItem>
          <SidebarItem href="/users">
            <AvatarIcon />
            <SidebarLabel>Users</SidebarLabel>
          </SidebarItem>
          {isAuthenticated && (
            <SidebarItem href="/sign-out">
              <ExitIcon />
              <SidebarLabel>Sign out</SidebarLabel>
            </SidebarItem>
          )}
        </SidebarSection>
        <SidebarSection>
          <SidebarHeading>Resources</SidebarHeading>
          <SidebarItem href="https://github.com/mdrideout/junjo" target="_blank">
            <RocketIcon />
            <SidebarLabel>
              <div className="flex items-center gap-x-2">
                junjo docs <ExternalLinkIcon className="size-3" />
              </div>
            </SidebarLabel>
          </SidebarItem>
          <SidebarItem href="https://github.com/mdrideout/junjo-ui" target="_blank">
            <GitHubLogoIcon />
            <SidebarLabel>
              <div className="flex items-center gap-x-2">
                junjo-ui github <ExternalLinkIcon className="size-3" />
              </div>
            </SidebarLabel>
          </SidebarItem>
          <SidebarItem href="https://github.com/mdrideout/junjo" target="_blank">
            <GitHubLogoIcon />
            <SidebarLabel>
              <div className="flex items-center gap-x-2">
                junjo github <ExternalLinkIcon className="size-3" />
              </div>
            </SidebarLabel>
          </SidebarItem>
        </SidebarSection>
      </SidebarBody>
    </Sidebar>
  )
}

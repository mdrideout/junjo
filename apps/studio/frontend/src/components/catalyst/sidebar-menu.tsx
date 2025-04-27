import {
  AvatarIcon,
  BarChartIcon,
  DashboardIcon,
  ExitIcon,
  ExternalLinkIcon,
  GitHubLogoIcon,
  RocketIcon,
  RowsIcon,
} from '@radix-ui/react-icons'
import { Link } from './link'
import { Sidebar, SidebarBody, SidebarHeading, SidebarItem, SidebarLabel, SidebarSection } from './sidebar'
import { AuthContext } from '../../auth/auth-context'
import { useContext } from 'react'
import junjoLogo from '../../assets/junjo-logo.svg'

export default function SidebarMenu() {
  const { isAuthenticated } = useContext(AuthContext)

  return (
    <Sidebar>
      <SidebarBody>
        <div className="mb-2 flex">
          <Link href="#" aria-label="Home">
            <div className="flex items-center gap-x-3 mb-2">
              <img
                src={junjoLogo}
                alt="Junjo Logo (Karp)"
                className="h-12 w-12 text-red dark:bg-zinc-50 dark:p-1 dark:mr-1 rounded-full"
              />
              <div className="font-logo text-3xl -mt-[2px]">j u n j o</div>
            </div>
          </Link>
        </div>
        <SidebarSection>
          {!isAuthenticated && (
            <SidebarItem href="/sign-in">
              <AvatarIcon />
              <SidebarLabel>Sign in</SidebarLabel>
            </SidebarItem>
          )}

          {isAuthenticated && (
            <>
              <SidebarItem href="/">
                <DashboardIcon />
                <SidebarLabel>Dashboard</SidebarLabel>
              </SidebarItem>
              <SidebarItem href="/logs">
                <RowsIcon />
                <SidebarLabel>Logs</SidebarLabel>
              </SidebarItem>
              <SidebarItem href="/users">
                <AvatarIcon />
                <SidebarLabel>Users</SidebarLabel>
              </SidebarItem>
              <SidebarItem href="//localhost/jaeger" target="_blank">
                <BarChartIcon />
                <SidebarLabel>
                  <div className="flex items-center gap-x-2">
                    Jaeger <ExternalLinkIcon className="size-3" />
                  </div>
                </SidebarLabel>
              </SidebarItem>

              <SidebarItem href="/sign-out">
                <ExitIcon />
                <SidebarLabel>Sign out</SidebarLabel>
              </SidebarItem>
            </>
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
          <SidebarItem href="https://github.com/mdrideout/junjo-server" target="_blank">
            <GitHubLogoIcon />
            <SidebarLabel>
              <div className="flex items-center gap-x-2">
                junjo-server github <ExternalLinkIcon className="size-3" />
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

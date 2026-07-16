import { Dialog } from '@base-ui/react/dialog'
import {
  AvatarIcon,
  Cross1Icon,
  DashboardIcon,
  ExitIcon,
  ExternalLinkIcon,
  GearIcon,
  GitHubLogoIcon,
  HamburgerMenuIcon,
  LockClosedIcon,
  LightningBoltIcon,
  RocketIcon,
  RowsIcon,
} from '@radix-ui/react-icons'
import clsx from 'clsx'
import { useState, type ComponentType, type ReactNode } from 'react'
import { Link, NavLink } from 'react-router'
import junjoLogo from '../../assets/junjo-logo.svg'
import { AppLink } from '../navigation/app-link'

interface AppShellProps {
  children: ReactNode
  isAuthenticated: boolean
}

interface NavigationItem {
  end?: boolean
  icon: ComponentType
  label: string
  to: string
}

const signedInNavigation: NavigationItem[] = [
  { end: true, icon: DashboardIcon, label: 'Dashboard', to: '/' },
  { icon: RowsIcon, label: 'Logs', to: '/logs' },
  { icon: LightningBoltIcon, label: 'Agents', to: '/agents' },
  { icon: AvatarIcon, label: 'Users', to: '/users' },
  { icon: LockClosedIcon, label: 'API Keys', to: '/api-keys' },
  { icon: GearIcon, label: 'Settings', to: '/settings' },
  { icon: ExitIcon, label: 'Sign out', to: '/sign-out' },
]

const signedOutNavigation: NavigationItem[] = [{ icon: AvatarIcon, label: 'Sign in', to: '/sign-in' }]

function Brand() {
  return (
    <Link
      to="/"
      aria-label="Junjo Studio home"
      className="flex items-center gap-3 rounded-lg focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--studio-focus-ring)]"
    >
      <img src={junjoLogo} alt="" className="size-11 rounded-full bg-white p-1 shadow-sm" />
      <span className="font-logo text-2xl tracking-wide text-[var(--studio-text)]">j u n j o</span>
    </Link>
  )
}

function Navigation({ isAuthenticated, onNavigate }: { isAuthenticated: boolean; onNavigate?: () => void }) {
  const navigation = isAuthenticated ? signedInNavigation : signedOutNavigation

  return (
    <div className="flex h-full flex-col" data-studio-navigation>
      <Brand />
      <nav aria-label="Primary" className="mt-8 flex flex-col gap-1">
        {navigation.map(({ end, icon: Icon, label, to }) => (
          <NavLink
            key={to}
            to={to}
            end={end}
            onClick={onNavigate}
            className={({ isActive }) =>
              clsx(
                'flex min-h-10 items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors',
                'focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--studio-focus-ring)]',
                isActive
                  ? 'bg-[var(--studio-navigation-active)] text-[var(--studio-navigation-active-text)]'
                  : 'text-[var(--studio-text-muted)] hover:bg-[var(--studio-surface-hover)] hover:text-[var(--studio-text)]',
              )
            }
          >
            <Icon />
            <span>{label}</span>
          </NavLink>
        ))}
      </nav>

      <nav aria-label="Resources" className="mt-auto border-t border-[var(--studio-border)] pt-6">
        <p className="mb-2 px-3 text-xs font-semibold uppercase tracking-[0.14em] text-[var(--studio-text-subtle)]">
          Resources
        </p>
        <div className="flex flex-col gap-1">
          <AppLink href="https://junjo.ai/docs/python/" newTab appearance="navigation" onClick={onNavigate}>
            <RocketIcon />
            <span className="flex items-center gap-2">
              SDK docs <ExternalLinkIcon />
            </span>
          </AppLink>
          <AppLink
            href="https://github.com/mdrideout/junjo/tree/master/apps/studio"
            newTab
            appearance="navigation"
            onClick={onNavigate}
          >
            <GitHubLogoIcon />
            <span className="flex items-center gap-2">
              Studio source <ExternalLinkIcon />
            </span>
          </AppLink>
          <AppLink
            href="https://github.com/mdrideout/junjo"
            newTab
            appearance="navigation"
            onClick={onNavigate}
          >
            <GitHubLogoIcon />
            <span className="flex items-center gap-2">
              Junjo source <ExternalLinkIcon />
            </span>
          </AppLink>
        </div>
      </nav>
    </div>
  )
}

/** Responsive Studio frame with authenticated navigation. */
export function AppShell({ children, isAuthenticated }: AppShellProps) {
  const [mobileNavigationOpen, setMobileNavigationOpen] = useState(false)

  return (
    <Dialog.Root open={mobileNavigationOpen} onOpenChange={setMobileNavigationOpen}>
      <div className="min-h-dvh bg-[var(--studio-page)] text-[var(--studio-text)] lg:flex">
        <aside className="sticky top-0 hidden h-dvh shrink-0 border-r border-[var(--studio-border)] bg-[var(--studio-surface)] p-3 pr-6 lg:block">
          <Navigation isAuthenticated={isAuthenticated} />
        </aside>

        <header className="sticky top-0 z-20 flex h-16 items-center gap-3 border-b border-[var(--studio-border)] bg-[var(--studio-surface)] px-4 lg:hidden">
          <Dialog.Trigger
            aria-label="Open navigation"
            className={
              'grid size-10 place-items-center rounded-lg text-[var(--studio-text)] ' +
              'hover:bg-[var(--studio-surface-hover)] focus-visible:outline-2 focus-visible:outline-offset-2 ' +
              'focus-visible:outline-[var(--studio-focus-ring)]'
            }
          >
            <HamburgerMenuIcon className="size-5" />
          </Dialog.Trigger>
          <span className="font-logo text-lg tracking-wide">j u n j o</span>
        </header>

        <main className="min-h-dvh min-w-0 flex-1">{children}</main>
      </div>

      <Dialog.Portal>
        <Dialog.Backdrop
          className={
            'fixed inset-0 z-50 bg-slate-950/65 transition-opacity duration-150 lg:hidden ' +
            'data-[starting-style]:opacity-0 data-[ending-style]:opacity-0'
          }
        />
        <Dialog.Viewport className="fixed inset-0 z-50 flex justify-start lg:hidden">
          <Dialog.Popup
            className={
              'relative h-dvh w-[min(20rem,88vw)] overflow-y-auto border-r border-[var(--studio-border)] ' +
              'bg-[var(--studio-surface)] p-6 shadow-2xl transition-transform duration-150 ' +
              'data-[starting-style]:-translate-x-full data-[ending-style]:-translate-x-full'
            }
          >
            <Dialog.Title className="sr-only">Studio navigation</Dialog.Title>
            <Dialog.Description className="sr-only">
              Navigate between Studio features and resources.
            </Dialog.Description>
            <Dialog.Close
              aria-label="Close navigation"
              className={
                'absolute right-4 top-4 grid size-9 place-items-center rounded-lg text-[var(--studio-text-muted)] ' +
                'hover:bg-[var(--studio-surface-hover)] hover:text-[var(--studio-text)] ' +
                'focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--studio-focus-ring)]'
              }
            >
              <Cross1Icon />
            </Dialog.Close>
            <Navigation isAuthenticated={isAuthenticated} onNavigate={() => setMobileNavigationOpen(false)} />
          </Dialog.Popup>
        </Dialog.Viewport>
      </Dialog.Portal>
    </Dialog.Root>
  )
}

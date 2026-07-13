import clsx from 'clsx'
import type { MouseEventHandler, ReactNode } from 'react'
import { Link, type To } from 'react-router'

type Appearance = 'inline' | 'navigation'

interface SharedProps {
  'aria-label'?: string
  appearance?: Appearance
  children: ReactNode
  onClick?: MouseEventHandler<HTMLAnchorElement>
}

interface InternalAppLinkProps extends SharedProps {
  to: To
  href?: never
  newTab?: never
}

interface ExternalAppLinkProps extends SharedProps {
  href: string
  newTab?: boolean
  to?: never
}

export type AppLinkProps = InternalAppLinkProps | ExternalAppLinkProps

const linkClassName = (appearance: Appearance) =>
  clsx(
    'rounded-sm focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--studio-focus-ring)]',
    appearance === 'inline' &&
      'font-medium text-[var(--studio-link)] underline decoration-transparent underline-offset-3 hover:decoration-current',
    appearance === 'navigation' &&
      'flex min-h-10 items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium text-[var(--studio-text-muted)] hover:bg-[var(--studio-surface-hover)] hover:text-[var(--studio-text)]',
  )

/** Renders an internal Router link or a secure external anchor. */
export function AppLink(props: AppLinkProps) {
  if (props.to !== undefined) {
    const { appearance = 'inline', children, to, ...linkProps } = props
    return (
      <Link {...linkProps} to={to} className={linkClassName(appearance)}>
        {children}
      </Link>
    )
  }

  const { appearance = 'inline', children, href, newTab = false, ...anchorProps } = props

  return (
    <a
      {...anchorProps}
      href={href}
      className={linkClassName(appearance)}
      rel={newTab ? 'noopener noreferrer' : undefined}
      target={newTab ? '_blank' : undefined}
    >
      {children}
    </a>
  )
}

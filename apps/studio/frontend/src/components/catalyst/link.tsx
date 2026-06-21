import * as Headless from '@headlessui/react'
import React, { forwardRef } from 'react'
import { Link as RouterLink } from 'react-router'

function isInternalHref(href: string): boolean {
  return href.startsWith('/') && !href.startsWith('//')
}

export const Link = forwardRef(function Link(
  props: { href: string } & React.ComponentPropsWithoutRef<'a'>,
  ref: React.ForwardedRef<HTMLAnchorElement>,
) {
  const { href, ...anchorProps } = props

  return (
    <Headless.DataInteractive>
      {isInternalHref(href) ? (
        <RouterLink {...anchorProps} to={href} ref={ref} />
      ) : (
        <a {...anchorProps} href={href} ref={ref} />
      )}
    </Headless.DataInteractive>
  )
})

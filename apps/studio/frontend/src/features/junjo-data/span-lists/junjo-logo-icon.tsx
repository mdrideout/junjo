import type { ImgHTMLAttributes } from 'react'
import junjoLogo from '../../../assets/junjo-logo.svg'

/** Canonical Junjo fish mark for native Junjo execution boundaries. */
export function JunjoLogoIcon(props: ImgHTMLAttributes<HTMLImageElement>) {
  return <img src={junjoLogo} alt="" aria-hidden="true" data-span-icon="junjo" {...props} />
}

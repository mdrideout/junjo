import { Button as BaseButton } from '@base-ui/react/button'
import clsx from 'clsx'
import type { ComponentPropsWithoutRef } from 'react'

type NativeButtonProps = Omit<ComponentPropsWithoutRef<'button'>, 'className' | 'style'>

export interface ActionButtonProps extends NativeButtonProps {
  intent?: 'primary' | 'secondary' | 'danger'
  size?: 'compact' | 'standard'
}

/**
 * Studio's semantic action control. Base UI owns button interaction behavior;
 * Junjo owns the visual contract exposed here.
 */
export function ActionButton({
  children,
  intent = 'primary',
  size = 'standard',
  type = 'button',
  ...buttonProps
}: ActionButtonProps) {
  return (
    <BaseButton
      {...buttonProps}
      type={type}
      className={clsx(
        'inline-flex items-center justify-center gap-2 rounded-lg font-semibold transition-colors',
        'focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--studio-focus-ring)]',
        'data-[disabled]:cursor-not-allowed data-[disabled]:opacity-45',
        size === 'compact' ? 'min-h-8 px-2.5 text-xs' : 'min-h-10 px-4 text-sm',
        intent === 'primary' &&
          'bg-[var(--studio-action-primary)] text-white hover:bg-[var(--studio-action-primary-hover)]',
        intent === 'secondary' &&
          'border border-[var(--studio-border-strong)] bg-[var(--studio-surface-raised)] text-[var(--studio-text)] hover:bg-[var(--studio-surface-hover)]',
        intent === 'danger' &&
          'bg-[var(--studio-action-danger)] text-white hover:bg-[var(--studio-action-danger-hover)]',
      )}
    >
      {children}
    </BaseButton>
  )
}

import { Dialog } from '@base-ui/react/dialog'
import clsx from 'clsx'
import type { ReactNode } from 'react'

export interface ModalProps {
  children: ReactNode
  description: ReactNode
  onOpenChange: (open: boolean) => void
  open: boolean
  size?: 'standard' | 'large' | 'wide'
  title: ReactNode
}

/**
 * Studio's modal boundary. Feature code supplies content while Base UI owns
 * focus management, dismissal, scroll locking, and ARIA relationships.
 */
export function Modal({ children, description, onOpenChange, open, size = 'standard', title }: ModalProps) {
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Backdrop
          className={
            'fixed inset-0 z-50 bg-slate-950/60 backdrop-blur-[2px] transition-opacity duration-150 ' +
            'data-[starting-style]:opacity-0 data-[ending-style]:opacity-0'
          }
        />
        <Dialog.Viewport className="fixed inset-0 z-50 flex items-center justify-center overflow-y-auto p-4 sm:p-8">
          <Dialog.Popup
            className={clsx(
              'relative my-auto max-h-[calc(100dvh-2rem)] w-full overflow-y-auto rounded-2xl',
              'border border-[var(--studio-border)] bg-[var(--studio-surface-raised)] p-6 text-[var(--studio-text)] shadow-2xl',
              'transition-[opacity,transform] duration-150 data-[starting-style]:scale-[0.98] data-[starting-style]:opacity-0',
              'data-[ending-style]:scale-[0.98] data-[ending-style]:opacity-0',
              size === 'standard' && 'max-w-lg',
              size === 'large' && 'max-w-2xl',
              size === 'wide' && 'max-w-4xl',
            )}
          >
            <Dialog.Title className="pr-10 text-xl font-semibold tracking-tight">{title}</Dialog.Title>
            <Dialog.Description className="mt-2 text-sm leading-6 text-[var(--studio-text-muted)]">
              {description}
            </Dialog.Description>
            <div className="mt-6">{children}</div>
            <Dialog.Close
              aria-label="Close dialog"
              className={
                'absolute right-4 top-4 grid size-9 place-items-center rounded-full text-xl leading-none ' +
                'text-[var(--studio-text-muted)] hover:bg-[var(--studio-surface-hover)] hover:text-[var(--studio-text)] ' +
                'focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--studio-focus-ring)]'
              }
            >
              <span aria-hidden="true">×</span>
            </Dialog.Close>
          </Dialog.Popup>
        </Dialog.Viewport>
      </Dialog.Portal>
    </Dialog.Root>
  )
}

export function ModalFooter({ children }: { children: ReactNode }) {
  return (
    <div className="mt-7 flex flex-wrap items-center justify-end gap-3 border-t border-[var(--studio-border)] pt-5">
      {children}
    </div>
  )
}

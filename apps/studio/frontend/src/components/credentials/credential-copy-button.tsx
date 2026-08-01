import { CopyIcon } from '@radix-ui/react-icons'
import { useEffect, useRef, useState } from 'react'

interface CredentialCopyButtonProps {
  label: string
  value: string
}

export function CredentialCopyButton({ label, value }: CredentialCopyButtonProps) {
  const [copied, setCopied] = useState(false)
  const resetTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(
    () => () => {
      if (resetTimer.current !== null) clearTimeout(resetTimer.current)
    },
    [],
  )

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(value)
      setCopied(true)
      if (resetTimer.current !== null) clearTimeout(resetTimer.current)
      resetTimer.current = setTimeout(() => setCopied(false), 1_000)
    } catch {
      alert(`Failed to copy ${label}.`)
    }
  }

  return (
    <button
      type="button"
      aria-label={`Copy ${label}`}
      title={copied ? 'Copied' : `Copy ${label}`}
      onClick={copy}
      className={
        'rounded-md p-1 transition-colors duration-300 ' +
        (copied
          ? 'bg-green-300 dark:bg-green-700'
          : 'hover:bg-[var(--studio-surface-hover)]')
      }
    >
      <CopyIcon className="size-4" />
    </button>
  )
}

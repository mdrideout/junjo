import { ReloadIcon } from '@radix-ui/react-icons'
import clsx from 'clsx'

interface RefreshButtonProps {
  onClick: () => void
  disabled: boolean
  isRefreshing: boolean
}

export default function RefreshButton({ onClick, disabled, isRefreshing }: RefreshButtonProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className="p-2 rounded hover:bg-zinc-100 dark:hover:bg-zinc-800 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
      title="Refresh models from provider API"
    >
      <ReloadIcon className={clsx('w-4 h-4', { 'animate-spin': isRefreshing })} />
    </button>
  )
}

import clsx from 'clsx'
import type { ParsedModelInfo } from '../../utils/model-grouping'

interface ModelCardProps {
  model: ParsedModelInfo
  isSelected: boolean
  onSelect: () => void
}

export default function ModelCard({ model, isSelected, onSelect }: ModelCardProps) {
  const { original, displayName } = model

  return (
    <button
      type="button"
      onClick={onSelect}
      className={clsx(
        'text-left p-3 rounded-lg border transition-colors cursor-pointer',
        isSelected
          ? 'border-indigo-500 bg-indigo-50 dark:bg-indigo-950/30'
          : 'border-zinc-200 dark:border-zinc-700 hover:border-zinc-300 dark:hover:border-zinc-600 hover:bg-zinc-50 dark:hover:bg-zinc-800/50',
      )}
    >
      <div className="flex items-start justify-between">
        <div className="flex-1">
          <div className="flex items-baseline gap-1">
            <span className="font-medium text-sm text-zinc-900 dark:text-zinc-100">{displayName}</span>{' '}
            <span className="text-xs text-zinc-500 dark:text-zinc-400">{original.id}</span>
          </div>

          <div className="flex gap-3 mt-2 text-xs text-zinc-500 dark:text-zinc-400">
            {original.max_tokens && (
              <span>
                <span className="font-medium">Max tokens:</span> {original.max_tokens.toLocaleString()}
              </span>
            )}
            {original.supports_reasoning && (
              <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-purple-100 text-purple-800 dark:bg-purple-900 dark:text-purple-200">
                Reasoning
              </span>
            )}
            {original.supports_vision && (
              <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200">
                Vision
              </span>
            )}
          </div>
        </div>
        {isSelected && (
          <div className="ml-3 flex-shrink-0">
            <div className="w-5 h-5 rounded-full bg-indigo-600 flex items-center justify-center">
              <svg className="w-3 h-3 text-white" fill="currentColor" viewBox="0 0 12 12">
                <path d="M10 3L4.5 8.5L2 6" stroke="currentColor" strokeWidth="2" fill="none" />
              </svg>
            </div>
          </div>
        )}
      </div>
    </button>
  )
}

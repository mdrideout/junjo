import type { ModelInfo } from '../../fetch/model-discovery'

interface OriginalModelCardProps {
  model: ModelInfo
  onSelect: () => void
}

export default function OriginalModelCard({ model, onSelect }: OriginalModelCardProps) {
  return (
    <button
      type="button"
      onClick={onSelect}
      className="w-full text-left p-3 rounded-lg border border-blue-300 bg-blue-50 dark:border-blue-700 dark:bg-blue-950/20 hover:bg-blue-100 dark:hover:bg-blue-950/30 transition-colors cursor-pointer"
    >
      <div className="flex items-start justify-between">
        <div className="flex-1">
          <div className="flex items-baseline gap-1">
            <span className="font-medium text-sm text-zinc-900 dark:text-zinc-100">
              {model.display_name || model.id}
            </span>
          </div>
          <div className="text-xs text-zinc-500 dark:text-zinc-400 mt-0.5">{model.id}</div>
          <div className="flex gap-3 mt-2 text-xs text-zinc-500 dark:text-zinc-400">
            {model.max_tokens && (
              <span>
                <span className="font-medium">Max tokens:</span> {model.max_tokens.toLocaleString()}
              </span>
            )}
            {model.supports_reasoning && (
              <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-purple-100 text-purple-800 dark:bg-purple-900 dark:text-purple-200">
                Reasoning
              </span>
            )}
            {model.supports_vision && (
              <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200">
                Vision
              </span>
            )}
          </div>
        </div>
        <div className="ml-3 flex-shrink-0">
          <span className="text-xs px-2 py-1 rounded bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200 font-medium">
            Use Original
          </span>
        </div>
      </div>
    </button>
  )
}

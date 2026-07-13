import { ExclamationTriangleIcon } from '@heroicons/react/24/solid'

interface ProviderWarningBannerProps {
  onClick: () => void
}

export default function ProviderWarningBanner({ onClick }: ProviderWarningBannerProps) {
  return (
    <button
      onClick={onClick}
      className="w-full mb-4 px-3 py-2 text-xs bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800 rounded-md text-amber-800 dark:text-amber-200 hover:bg-amber-100 dark:hover:bg-amber-900/30 transition-colors text-left flex items-start gap-2"
    >
      <ExclamationTriangleIcon className="size-4 flex-shrink-0 mt-0.5" />
      <div>
        <div className="font-semibold">Schema telemetry issue detected</div>
        <div className="text-amber-700 dark:text-amber-300">
          Click for details on improving observability with response_json_schema
        </div>
      </div>
    </button>
  )
}

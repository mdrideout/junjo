import { InformationCircleIcon } from '@heroicons/react/24/solid'

interface JsonSchemaBannerProps {
  onClick: () => void
}

export default function JsonSchemaBanner({ onClick }: JsonSchemaBannerProps) {
  return (
    <button
      onClick={onClick}
      className="w-full mb-4 px-3 py-2 text-xs bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-md text-blue-800 dark:text-blue-200 hover:bg-blue-100 dark:hover:bg-blue-900/30 transition-colors text-left flex items-start gap-2"
    >
      <InformationCircleIcon className="size-4 flex-shrink-0 mt-0.5" />
      <div>
        <div className="font-semibold">JSON Schema detected and active</div>
        <div className="text-blue-700 dark:text-blue-300">
          Playground requests will use this schema for structured output. Click to view schema details.
        </div>
      </div>
    </button>
  )
}

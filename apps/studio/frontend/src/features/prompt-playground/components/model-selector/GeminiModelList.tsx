import type { ProductFamilyGroup } from '../../utils/model-grouping'
import ModelCard from './ModelCard'

interface GeminiModelListProps {
  familyGroup: ProductFamilyGroup
  selectedModel: string | null
  onSelectModel: (modelId: string) => void
}

export default function GeminiModelList({
  familyGroup,
  selectedModel,
  onSelectModel,
}: GeminiModelListProps) {
  return (
    <div>
      {familyGroup.versionGroups.map((versionGroup) => (
        <div key={versionGroup.version} className="mb-4 last:mb-0">
          {/* Version Header */}
          {versionGroup.version && (
            <p className="text-sm font-bold text-zinc-700 dark:text-zinc-300 mb-2">
              {versionGroup.version === 'latest' || versionGroup.version === '0.0' ? 'Latest' : `Version ${versionGroup.version}`}
            </p>
          )}

          {/* Release Type Groups */}
          {versionGroup.releaseTypeGroups.map((releaseTypeGroup) => (
            <div key={releaseTypeGroup.releaseType} className="mb-3 last:mb-0">
              {/* Release Type Header */}
              <p className="text-xs font-semibold text-zinc-600 dark:text-zinc-400 mb-2 pl-2">
                {releaseTypeGroup.displayName}
              </p>

              {/* Model Cards */}
              <div className="grid grid-cols-1 gap-2">
                {releaseTypeGroup.models.map((model) => (
                  <ModelCard
                    key={model.original.id}
                    model={model}
                    isSelected={model.original.id === selectedModel}
                    onSelect={() => onSelectModel(model.original.id)}
                  />
                ))}
              </div>
            </div>
          ))}
        </div>
      ))}
    </div>
  )
}

import type { ProductFamilyGroup } from '../../utils/model-grouping'
import ModelCard from './ModelCard'

interface AnthropicModelListProps {
  familyGroup: ProductFamilyGroup
  selectedModel: string | null
  onSelectModel: (modelId: string) => void
}

export default function AnthropicModelList({
  familyGroup,
  selectedModel,
  onSelectModel,
}: AnthropicModelListProps) {
  return (
    <div>
      {/* Product Family Header */}
      <h3 className="text-base font-bold text-zinc-900 dark:text-zinc-100 mb-3">
        {familyGroup.displayName}
      </h3>

      {/* Flat list of models */}
      <div className="grid grid-cols-1 gap-2">
        {familyGroup.versionGroups.flatMap((versionGroup) =>
          versionGroup.releaseTypeGroups.flatMap((releaseTypeGroup) =>
            releaseTypeGroup.models.map((model) => (
              <ModelCard
                key={model.original.id}
                model={model}
                isSelected={model.original.id === selectedModel}
                onSelect={() => onSelectModel(model.original.id)}
              />
            ))
          )
        )}
      </div>
    </div>
  )
}

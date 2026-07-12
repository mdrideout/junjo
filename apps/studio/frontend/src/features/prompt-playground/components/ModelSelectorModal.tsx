import { useState, useMemo } from 'react'
import { Button } from '../../../components/catalyst/button'
import {
  Dialog,
  DialogActions,
  DialogBody,
  DialogDescription,
  DialogTitle,
} from '../../../components/catalyst/dialog'
import type { ModelInfo } from '../fetch/model-discovery'
import {
  organizeModels,
  type ProductFamilyGroup,
} from '../utils/model-grouping'
import RefreshButton from './RefreshButton'
import ModelCard from './model-selector/ModelCard'
import OriginalModelCard from './model-selector/OriginalModelCard'
import GeminiModelList from './model-selector/GeminiModelList'
import OpenAIModelList from './model-selector/OpenAIModelList'
import AnthropicModelList from './model-selector/AnthropicModelList'

interface ModelSelectorModalProps {
  isOpen: boolean
  onClose: () => void
  models: ModelInfo[]
  provider: string | null
  selectedModel: string | null
  originalModelId: string | null
  onSelectModel: (modelId: string) => void
  onRefresh: () => void
  isRefreshing: boolean
  error: string | null
}

export default function ModelSelectorModal({
  isOpen,
  onClose,
  models,
  provider,
  selectedModel,
  originalModelId,
  onSelectModel,
  onRefresh,
  isRefreshing,
  error,
}: ModelSelectorModalProps) {
  // Filter state (preview and exp default to off)
  const [includeStable, setIncludeStable] = useState(true)
  const [includePreview, setIncludePreview] = useState(false)
  const [includeExp, setIncludeExp] = useState(false)
  const [includeDated, setIncludeDated] = useState(false) // Dated models default to off

  // Find the original model info
  const originalModel =
    originalModelId && originalModelId !== 'Unknown' ? models.find((m) => m.id === originalModelId) : null

  // Group and filter models
  const productFamilyGroups = useMemo(
    () => organizeModels(models, provider, { includeStable, includePreview, includeExp, includeDated }),
    [models, provider, includeStable, includePreview, includeExp, includeDated]
  )

  const handleSelectModel = (modelId: string) => {
    onSelectModel(modelId)
    onClose()
  }

  return (
    <Dialog open={isOpen} onClose={onClose} size="3xl">
      <DialogTitle>Select Model</DialogTitle>
      <DialogDescription>
        {provider === 'gemini'
          ? 'Choose a model from the available Gemini models. Filter by release type to narrow your selection.'
          : provider === 'openai'
          ? 'Choose a model from the available OpenAI models. Filter by release type to narrow your selection.'
          : `Choose a model from the available ${provider} models.`}
      </DialogDescription>
      <DialogBody>
        {/* Original Model Card */}
        {originalModel && (
          <div className="-mt-3 mb-4 pb-4 border-b border-zinc-200 dark:border-zinc-700">
            <OriginalModelCard model={originalModel} onSelect={() => handleSelectModel(originalModel.id)} />
          </div>
        )}

        {/* Filter Controls and Refresh (for Gemini and OpenAI) */}
        {(provider === 'gemini' || provider === 'openai') && (
          <div className="mb-4 pb-4 border-b border-zinc-200 dark:border-zinc-700">
            <div className="flex items-center justify-between gap-4">
              <div className="flex flex-wrap gap-4">
                <label className="flex items-center gap-2 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={includeStable}
                    onChange={(e) => setIncludeStable(e.target.checked)}
                    className="w-4 h-4 text-indigo-600 border-zinc-300 rounded focus:ring-indigo-500"
                  />
                  <span className="text-sm text-zinc-700 dark:text-zinc-300">Stable</span>
                </label>
                <label className="flex items-center gap-2 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={includePreview}
                    onChange={(e) => setIncludePreview(e.target.checked)}
                    className="w-4 h-4 text-indigo-600 border-zinc-300 rounded focus:ring-indigo-500"
                  />
                  <span className="text-sm text-zinc-700 dark:text-zinc-300">Preview</span>
                </label>
                {provider === 'gemini' && (
                  <label className="flex items-center gap-2 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={includeExp}
                      onChange={(e) => setIncludeExp(e.target.checked)}
                      className="w-4 h-4 text-indigo-600 border-zinc-300 rounded focus:ring-indigo-500"
                    />
                    <span className="text-sm text-zinc-700 dark:text-zinc-300">Experimental</span>
                  </label>
                )}
                {provider === 'openai' && (
                  <label className="flex items-center gap-2 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={includeDated}
                      onChange={(e) => setIncludeDated(e.target.checked)}
                      className="w-4 h-4 text-indigo-600 border-zinc-300 rounded focus:ring-indigo-500"
                    />
                    <span className="text-sm text-zinc-700 dark:text-zinc-300">Dated Models</span>
                  </label>
                )}
              </div>
              <RefreshButton onClick={onRefresh} disabled={isRefreshing} isRefreshing={isRefreshing} />
            </div>
          </div>
        )}

        {/* Refresh Button (for other providers without filters) */}
        {provider && provider !== 'gemini' && provider !== 'openai' && (
          <div className="mb-4 pb-4 border-b border-zinc-200 dark:border-zinc-700">
            <div className="flex justify-end">
              <RefreshButton onClick={onRefresh} disabled={isRefreshing} isRefreshing={isRefreshing} />
            </div>
          </div>
        )}

        {/* Error Display */}
        {error && (
          <div className="mb-4 p-4 rounded-lg bg-red-50 dark:bg-red-950/20 border border-red-200 dark:border-red-800">
            <div className="flex items-start gap-3">
              <svg
                className="w-5 h-5 text-red-600 dark:text-red-400 flex-shrink-0 mt-0.5"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
                />
              </svg>
              <div className="flex-1">
                <h4 className="text-sm font-semibold text-red-800 dark:text-red-200 mb-1">
                  Failed to Load Models
                </h4>
                <p className="text-sm text-red-700 dark:text-red-300">{error}</p>
                {(error.includes('Failed to fetch models') || error.includes('Failed to refresh models')) && (
                  <p className="text-xs text-red-600 dark:text-red-400 mt-2">
                    This may be due to a missing or invalid API key. Check your .env file and ensure the API key
                    for {provider} is configured.
                  </p>
                )}
              </div>
            </div>
          </div>
        )}

        {/* Model Groups */}
        <div className="space-y-6">
          {productFamilyGroups.length === 0 ? (
            <div className="text-center py-8 text-zinc-500 dark:text-zinc-400">
              No models match the selected filters.
            </div>
          ) : (
            productFamilyGroups.map((familyGroup) => (
              <ProductFamilySection
                key={familyGroup.productFamily}
                familyGroup={familyGroup}
                selectedModel={selectedModel}
                onSelectModel={handleSelectModel}
                provider={provider}
              />
            ))
          )}
        </div>

        <DialogActions>
          <Button plain onClick={onClose}>
            Cancel
          </Button>
        </DialogActions>
      </DialogBody>
    </Dialog>
  )
}

interface ProductFamilySectionProps {
  familyGroup: ProductFamilyGroup
  selectedModel: string | null
  onSelectModel: (modelId: string) => void
  provider: string | null
}

function ProductFamilySection({
  familyGroup,
  selectedModel,
  onSelectModel,
  provider,
}: ProductFamilySectionProps) {
  if (provider === 'gemini') {
    return (
      <GeminiModelList
        familyGroup={familyGroup}
        selectedModel={selectedModel}
        onSelectModel={onSelectModel}
      />
    )
  }

  if (provider === 'openai') {
    return (
      <OpenAIModelList
        familyGroup={familyGroup}
        selectedModel={selectedModel}
        onSelectModel={onSelectModel}
      />
    )
  }

  if (provider === 'anthropic') {
    return (
      <AnthropicModelList
        familyGroup={familyGroup}
        selectedModel={selectedModel}
        onSelectModel={onSelectModel}
      />
    )
  }

  // Default rendering for unknown providers
  return (
    <div>
      <div className="grid grid-cols-1 gap-2">
        {familyGroup.versionGroups.flatMap((vg) =>
          vg.releaseTypeGroups.flatMap((rtg) =>
            rtg.models.map((model) => (
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

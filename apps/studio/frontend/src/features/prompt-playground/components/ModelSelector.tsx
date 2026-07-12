import { useAppDispatch, useAppSelector } from '../../../root-store/hooks'
import { PromptPlaygroundActions } from '../store/slice'
import { useEffect, useState, useMemo } from 'react'
import clsx from 'clsx'
import { fetchModelsByProvider, refreshModelsByProvider } from '../fetch/model-discovery'
import type { ModelInfo } from '../fetch/model-discovery'
import ModelSelectorModal from './ModelSelectorModal'

interface ModelSelectorProps {
  originalModel: string | null
  originalProvider: string | null
  provider: string | null
}

export default function ModelSelector(props: ModelSelectorProps) {
  const { originalModel, originalProvider, provider } = props
  const dispatch = useAppDispatch()
  const selectedModel = useAppSelector((state) => state.promptPlaygroundState.selectedModel)
  const [models, setModels] = useState<ModelInfo[]>([])
  const [isFetching, setIsFetching] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [modalOpen, setModalOpen] = useState(false)

  // Fetch models when provider changes
  useEffect(() => {
    if (!provider) {
      setModels([])
      setError(null)
      return
    }

    const fetchModels = async () => {
      setIsFetching(true)
      setError(null)
      try {
        const fetchedModels = await fetchModelsByProvider(provider)
        setModels(fetchedModels)
        setError(null)
      } catch (error) {
        console.error('Failed to fetch models:', error)
        const errorMessage = error instanceof Error ? error.message : 'Failed to fetch models'
        setError(errorMessage)
        setModels([])
      } finally {
        setIsFetching(false)
      }
    }

    fetchModels()
  }, [provider])

  // Handle refresh button click
  const handleRefresh = async () => {
    if (!provider) return

    setIsFetching(true)
    setError(null)
    try {
      const refreshedModels = await refreshModelsByProvider(provider)
      setModels(refreshedModels)
      setError(null)
    } catch (error) {
      console.error('Failed to refresh models:', error)
      const errorMessage = error instanceof Error ? error.message : 'Failed to refresh models'
      setError(errorMessage)
    } finally {
      setIsFetching(false)
    }
  }

  // Include original model from telemetry if not in fetched list (memoized)
  // Only include if the current provider matches the original provider
  const allModels = useMemo(() => {
    const result = [...models]
    if (
      originalModel &&
      originalModel !== 'Unknown' &&
      provider === originalProvider &&
      !models.find((m) => m.id === originalModel)
    ) {
      // Add original model with provider prefix format if not already present
      const modelId = originalModel.includes('/') ? originalModel : `${provider}/${originalModel}`
      // Extract display name (remove provider prefix if present)
      const displayName = originalModel.includes('/') ? originalModel.split('/')[1] : originalModel
      result.push({
        id: modelId,
        display_name: displayName,
        provider: provider || 'unknown',
        supports_reasoning: false,
        supports_vision: false,
        max_tokens: null,
      })
    }
    return result
  }, [models, originalModel, originalProvider, provider])

  const handleSelectModel = (modelId: string) => {
    dispatch(PromptPlaygroundActions.setSelectedModel(modelId))
  }

  const isDisabled = !provider || isFetching

  // Get display text for selected model
  const selectedModelDisplay = selectedModel || (isFetching ? 'Loading...' : !provider ? 'Select provider first' : 'Select a model')

  return (
    <div className="flex items-center gap-2">
      <button
        type="button"
        onClick={() => setModalOpen(true)}
        disabled={isDisabled}
        className="inline-flex items-center justify-center rounded px-[15px] text-[13px] leading-none h-[35px] gap-[5px] bg-white text-gray-900 shadow-[0_2px_10px] shadow-black/10 hover:bg-gray-100 focus:shadow-[0_0_0_2px] focus:shadow-black disabled:opacity-50 disabled:cursor-not-allowed outline-none"
        aria-label="Model"
      >
        <span className={clsx({ 'text-gray-500': !selectedModel })}>{selectedModelDisplay}</span>
        <svg className="w-4 h-4 text-gray-900" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
        </svg>
      </button>

      <ModelSelectorModal
        isOpen={modalOpen}
        onClose={() => setModalOpen(false)}
        models={allModels}
        provider={provider}
        selectedModel={selectedModel}
        originalModelId={originalModel}
        onSelectModel={handleSelectModel}
        onRefresh={handleRefresh}
        isRefreshing={isFetching}
        error={error}
      />
    </div>
  )
}

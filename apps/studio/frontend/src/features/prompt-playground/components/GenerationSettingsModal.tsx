import { useState, useEffect } from 'react'
import { ActionButton } from '../../../components/actions/action-button'
import { Switch } from '../../../components/forms/switch'
import { Modal, ModalFooter } from '../../../components/overlays/modal'
import type { GenerationSettings } from '../store/slice'

interface GenerationSettingsModalProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  provider: string | null
  model: string | null
  settings: GenerationSettings
  onSave: (settings: GenerationSettings) => void
}

// Detect if model is a reasoning model (OpenAI o1, o3, o4, gpt-5)
const isReasoningModel = (modelId: string | null): boolean => {
  if (!modelId) return false

  // Strip provider prefix (e.g., "openai/" or "google/")
  const modelWithoutProvider = modelId.includes('/') ? modelId.split('/')[1] : modelId

  // Check if it's a reasoning model
  return /^(o1-|o1$|o3-|o3$|o4-|o4$|gpt-5)/.test(modelWithoutProvider)
}

export default function GenerationSettingsModal({
  open,
  onOpenChange,
  provider,
  model,
  settings,
  onSave,
}: GenerationSettingsModalProps) {
  const [localSettings, setLocalSettings] = useState<GenerationSettings>(settings)

  // Reset local settings when modal opens or settings change
  useEffect(() => {
    if (open) {
      setLocalSettings(settings)
    }
  }, [open, settings])

  const handleSave = () => {
    onSave(localSettings)
    onOpenChange(false)
  }

  const handleReset = () => {
    setLocalSettings({})
  }

  const updateSetting = <K extends keyof GenerationSettings>(key: K, value: GenerationSettings[K]) => {
    setLocalSettings((prev) => ({
      ...prev,
      [key]: value,
    }))
  }

  const isReasoning = isReasoningModel(model)

  return (
    <Modal
      open={open}
      onOpenChange={onOpenChange}
      size="large"
      title="Generation Settings"
      description="Configure provider-specific generation parameters. Only set values you want to override from defaults."
    >
      <div className="space-y-6">
        {/* OpenAI Section */}
        {provider === 'openai' && (
          <div>
            <h3 className="text-sm font-semibold text-zinc-900 dark:text-zinc-100 mb-3">OpenAI Settings</h3>
            <div className="space-y-4">
              {isReasoning && (
                <div>
                  <label className="block text-sm font-medium text-zinc-700 dark:text-zinc-300 mb-1">
                    Reasoning Effort
                  </label>
                  <select
                    value={localSettings.reasoning_effort || ''}
                    onChange={(e) =>
                      updateSetting(
                        'reasoning_effort',
                        e.target.value as GenerationSettings['reasoning_effort'],
                      )
                    }
                    className="w-full px-3 py-2 border border-zinc-300 dark:border-zinc-700 rounded-md bg-white dark:bg-zinc-900 text-zinc-900 dark:text-zinc-100"
                  >
                    <option value="">Default (medium)</option>
                    <option value="minimal">Minimal</option>
                    <option value="low">Low</option>
                    <option value="medium">Medium</option>
                    <option value="high">High</option>
                  </select>
                  <p className="text-xs text-zinc-500 mt-1">
                    Controls how much the model thinks before responding. Higher = more thorough reasoning.
                  </p>
                </div>
              )}

              <div>
                <label className="block text-sm font-medium text-zinc-700 dark:text-zinc-300 mb-1">
                  Max Completion Tokens
                </label>
                <input
                  type="number"
                  min="1"
                  value={localSettings.max_completion_tokens || ''}
                  onChange={(e) =>
                    updateSetting(
                      'max_completion_tokens',
                      e.target.value ? Number(e.target.value) : undefined,
                    )
                  }
                  placeholder="Default"
                  className="w-full px-3 py-2 border border-zinc-300 dark:border-zinc-700 rounded-md bg-white dark:bg-zinc-900 text-zinc-900 dark:text-zinc-100"
                />
                <p className="text-xs text-zinc-500 mt-1">Maximum number of tokens to generate.</p>
              </div>

              {!isReasoning && (
                <div>
                  <label className="block text-sm font-medium text-zinc-700 dark:text-zinc-300 mb-1">
                    Temperature
                  </label>
                  <input
                    type="number"
                    min="0"
                    max="2"
                    step="0.1"
                    value={localSettings.temperature ?? ''}
                    onChange={(e) =>
                      updateSetting('temperature', e.target.value ? Number(e.target.value) : undefined)
                    }
                    placeholder="1.0 (default)"
                    className="w-full px-3 py-2 border border-zinc-300 dark:border-zinc-700 rounded-md bg-white dark:bg-zinc-900 text-zinc-900 dark:text-zinc-100"
                  />
                  <p className="text-xs text-zinc-500 mt-1">
                    Sampling temperature (0-2). Higher values = more random, lower = more focused.
                  </p>
                </div>
              )}

              {isReasoning && (
                <p className="text-xs text-amber-600 dark:text-amber-400 bg-amber-50 dark:bg-amber-950/20 p-2 rounded">
                  Temperature is not supported for reasoning models (o1, o3, o4, gpt-5 series)
                </p>
              )}
            </div>
          </div>
        )}

        {/* Anthropic Section */}
        {provider === 'anthropic' && (
          <div>
            <h3 className="text-sm font-semibold text-zinc-900 dark:text-zinc-100 mb-3">
              Anthropic Settings
            </h3>
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-zinc-700 dark:text-zinc-300 mb-1">
                  Extended Thinking
                </label>
                <select
                  value={localSettings.reasoning_effort || ''}
                  onChange={(e) =>
                    updateSetting(
                      'reasoning_effort',
                      e.target.value as GenerationSettings['reasoning_effort'],
                    )
                  }
                  className="w-full px-3 py-2 border border-zinc-300 dark:border-zinc-700 rounded-md bg-white dark:bg-zinc-900 text-zinc-900 dark:text-zinc-100"
                >
                  <option value="">Disabled</option>
                  <option value="low">Low (1024 tokens)</option>
                  <option value="medium">Medium (2048 tokens)</option>
                  <option value="high">High (4096 tokens)</option>
                </select>
                <p className="text-xs text-zinc-500 mt-1">
                  Enable Claude's extended reasoning process with visible thinking. Higher levels allocate
                  more tokens.
                </p>
              </div>

              <div>
                <label className="block text-sm font-medium text-zinc-700 dark:text-zinc-300 mb-1">
                  Temperature
                </label>
                <input
                  type="number"
                  min="0"
                  max="1"
                  step="0.1"
                  value={localSettings.temperature ?? ''}
                  onChange={(e) =>
                    updateSetting('temperature', e.target.value ? Number(e.target.value) : undefined)
                  }
                  placeholder="1.0 (default)"
                  className="w-full px-3 py-2 border border-zinc-300 dark:border-zinc-700 rounded-md bg-white dark:bg-zinc-900 text-zinc-900 dark:text-zinc-100"
                />
                <p className="text-xs text-zinc-500 mt-1">Sampling temperature (0-1).</p>
              </div>

              <div>
                <label className="block text-sm font-medium text-zinc-700 dark:text-zinc-300 mb-1">
                  Max Tokens
                </label>
                <input
                  type="number"
                  min="1"
                  value={localSettings.max_tokens || ''}
                  onChange={(e) =>
                    updateSetting('max_tokens', e.target.value ? Number(e.target.value) : undefined)
                  }
                  placeholder="4096 (default)"
                  className="w-full px-3 py-2 border border-zinc-300 dark:border-zinc-700 rounded-md bg-white dark:bg-zinc-900 text-zinc-900 dark:text-zinc-100"
                />
                <p className="text-xs text-zinc-500 mt-1">Maximum tokens to generate.</p>
              </div>
            </div>
          </div>
        )}

        {/* Gemini Section */}
        {provider === 'gemini' && (
          <div>
            <h3 className="text-sm font-semibold text-zinc-900 dark:text-zinc-100 mb-3">Gemini Settings</h3>
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-zinc-700 dark:text-zinc-300 mb-1">
                  Thinking Budget
                </label>
                <select
                  value={localSettings.thinkingBudget?.toString() || ''}
                  onChange={(e) => {
                    const value = e.target.value
                    updateSetting('thinkingBudget', value ? Number(value) : undefined)
                  }}
                  className="w-full px-3 py-2 border border-zinc-300 dark:border-zinc-700 rounded-md bg-white dark:bg-zinc-900 text-zinc-900 dark:text-zinc-100"
                >
                  <option value="">Model Default</option>
                  <option value="-1">Dynamic (auto-adjust based on complexity)</option>
                  <option value="0">Disabled (2.5 Flash/Flash-Lite only)</option>
                  <option value="1024">1024 tokens</option>
                  <option value="2048">2048 tokens</option>
                  <option value="4096">4096 tokens</option>
                  <option value="8192">8192 tokens</option>
                  <option value="16384">16384 tokens</option>
                  <option value="32768">32768 tokens (max)</option>
                </select>
                <p className="text-xs text-zinc-500 mt-1">
                  Tokens allocated for internal reasoning. Gemini 2.5 Pro requires thinking enabled.
                </p>
              </div>

              <Switch
                label="Include thoughts"
                description="Include synthesized thought summaries in the response."
                checked={localSettings.includeThoughts || false}
                onCheckedChange={(checked) => updateSetting('includeThoughts', checked)}
              />

              <div>
                <label className="block text-sm font-medium text-zinc-700 dark:text-zinc-300 mb-1">
                  Temperature
                </label>
                <input
                  type="number"
                  min="0"
                  max="2"
                  step="0.1"
                  value={localSettings.temperature ?? ''}
                  onChange={(e) =>
                    updateSetting('temperature', e.target.value ? Number(e.target.value) : undefined)
                  }
                  placeholder="1.0 (default)"
                  className="w-full px-3 py-2 border border-zinc-300 dark:border-zinc-700 rounded-md bg-white dark:bg-zinc-900 text-zinc-900 dark:text-zinc-100"
                />
                <p className="text-xs text-zinc-500 mt-1">Sampling temperature.</p>
              </div>

              <div>
                <label className="block text-sm font-medium text-zinc-700 dark:text-zinc-300 mb-1">
                  Max Output Tokens
                </label>
                <input
                  type="number"
                  min="1"
                  value={localSettings.maxOutputTokens || ''}
                  onChange={(e) =>
                    updateSetting('maxOutputTokens', e.target.value ? Number(e.target.value) : undefined)
                  }
                  placeholder="Model default"
                  className="w-full px-3 py-2 border border-zinc-300 dark:border-zinc-700 rounded-md bg-white dark:bg-zinc-900 text-zinc-900 dark:text-zinc-100"
                />
                <p className="text-xs text-zinc-500 mt-1">Maximum tokens to generate.</p>
              </div>
            </div>
          </div>
        )}

        {!provider && (
          <div className="text-center py-8 text-zinc-500 dark:text-zinc-400">
            Please select a provider first.
          </div>
        )}
      </div>
      <ModalFooter>
        <ActionButton intent="secondary" onClick={handleReset}>
          Reset All
        </ActionButton>
        <ActionButton intent="secondary" onClick={() => onOpenChange(false)}>
          Cancel
        </ActionButton>
        <ActionButton onClick={handleSave}>Save</ActionButton>
      </ModalFooter>
    </Modal>
  )
}

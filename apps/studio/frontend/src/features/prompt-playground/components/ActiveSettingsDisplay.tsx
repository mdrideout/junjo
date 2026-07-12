import type { GenerationSettings } from '../store/slice'

interface ActiveSettingsDisplayProps {
  settings: GenerationSettings
  provider: string | null
  jsonMode?: boolean
  hasSchema?: boolean
}

export default function ActiveSettingsDisplay({ settings, provider, jsonMode, hasSchema }: ActiveSettingsDisplayProps) {
  // Build list of active settings based on provider
  const activeSettings: string[] = []

  // Add JSON schema indicator if structured output is enabled and schema is available
  if (jsonMode && hasSchema) {
    activeSettings.push('json_schema: active')
  }

  if (provider === 'openai') {
    if (settings.reasoning_effort) {
      activeSettings.push(`reasoning_effort: ${settings.reasoning_effort}`)
    }
    if (settings.max_completion_tokens) {
      activeSettings.push(`max_completion_tokens: ${settings.max_completion_tokens}`)
    }
    if (settings.temperature !== undefined) {
      activeSettings.push(`temperature: ${settings.temperature}`)
    }
  } else if (provider === 'anthropic') {
    if (settings.thinking_enabled) {
      const budget = settings.thinking_budget_tokens ? ` (${settings.thinking_budget_tokens} tokens)` : ''
      activeSettings.push(`thinking: enabled${budget}`)
    }
    if (settings.temperature !== undefined) {
      activeSettings.push(`temperature: ${settings.temperature}`)
    }
    if (settings.max_tokens) {
      activeSettings.push(`max_tokens: ${settings.max_tokens}`)
    }
  } else if (provider === 'gemini') {
    if (settings.thinkingBudget !== undefined) {
      const budgetLabel =
        settings.thinkingBudget === -1
          ? 'dynamic'
          : settings.thinkingBudget === 0
          ? 'disabled'
          : `${settings.thinkingBudget} tokens`
      activeSettings.push(`thinkingBudget: ${budgetLabel}`)
    }
    if (settings.includeThoughts) {
      activeSettings.push(`includeThoughts: true`)
    }
    if (settings.temperature !== undefined) {
      activeSettings.push(`temperature: ${settings.temperature}`)
    }
    if (settings.maxOutputTokens) {
      activeSettings.push(`maxOutputTokens: ${settings.maxOutputTokens}`)
    }
  }

  // Don't render if no active settings
  if (activeSettings.length === 0) {
    return null
  }

  return (
    <div className="mb-4 text-xs text-zinc-600 dark:text-zinc-400">
      <span className="font-medium">Active settings:</span> {activeSettings.join(' • ')}
    </div>
  )
}

/**
 * Provider mapping utilities to handle differences between OpenInference
 * telemetry provider names and internal provider identifiers.
 *
 * OpenInference standard uses "google" for Gemini, but we use "gemini" internally.
 */

/**
 * Maps OpenInference provider names to internal provider names
 * @param otelProvider - Provider name from OpenInference telemetry (e.g., "google")
 * @returns Internal provider name (e.g., "gemini")
 */
export function mapOtelProviderToInternal(otelProvider: string): string {
  const mappings: Record<string, string> = {
    'google': 'gemini',
    'openai': 'openai',
    'anthropic': 'anthropic',
    'gemini': 'gemini', // Allow "gemini" directly for compatibility
    'cohere': 'cohere',
    'mistralai': 'mistralai',
    'azure': 'azure',
    'aws': 'aws',
  }

  const normalized = otelProvider.toLowerCase().trim()
  return mappings[normalized] || normalized
}

/**
 * Maps internal provider names back to OpenInference standard names
 * @param internalProvider - Internal provider name (e.g., "gemini")
 * @returns OpenInference provider name (e.g., "google")
 */
export function mapInternalProviderToOtel(internalProvider: string): string {
  const mappings: Record<string, string> = {
    'gemini': 'google',
    'openai': 'openai',
    'anthropic': 'anthropic',
    'cohere': 'cohere',
    'mistralai': 'mistralai',
    'azure': 'azure',
    'aws': 'aws',
  }

  const normalized = internalProvider.toLowerCase().trim()
  return mappings[normalized] || normalized
}

/**
 * Gets a human-friendly display name for a provider
 * @param provider - Provider identifier (either internal or OTEL format)
 * @returns Display name (e.g., "Google Gemini")
 */
export function getProviderDisplayName(provider: string): string {
  const displayNames: Record<string, string> = {
    'gemini': 'Google Gemini',
    'openai': 'OpenAI',
    'anthropic': 'Anthropic',
    'cohere': 'Cohere',
    'mistralai': 'Mistral AI',
    'azure': 'Azure',
    'aws': 'AWS Bedrock',
    'google': 'Google Gemini', // Handle both forms
  }

  const normalized = provider.toLowerCase().trim()
  if (displayNames[normalized]) {
    return displayNames[normalized]
  }

  // Return capitalized version as fallback
  if (normalized.length > 0) {
    return normalized.charAt(0).toUpperCase() + normalized.slice(1)
  }

  return provider
}

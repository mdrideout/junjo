/**
 * Model capability detection utilities for the Prompt Playground.
 *
 * These functions determine which generation parameters are supported
 * by different LLM models and providers.
 */

/**
 * Checks if a model supports the temperature parameter.
 *
 * OpenAI reasoning models (o1, o3, o4, gpt-5 series) do not support
 * temperature and only accept temperature=1.
 *
 * @param model - The model identifier (e.g., "openai/gpt-4", "openai/gpt-5-nano", "openai/o1-preview")
 * @returns true if the model supports temperature, false otherwise
 */
export function supportsTemperature(model: string): boolean {
  // Extract model name without provider prefix (e.g., "openai/gpt-5-nano" -> "gpt-5-nano")
  const modelName = model.includes('/') ? model.split('/')[1] : model

  // Reasoning models that don't support temperature
  // Pattern matches: o1, o1-*, o3, o3-*, o4, o4-*, gpt-5*
  const reasoningModelPattern = /^(o1-|o1$|o3-|o3$|o4-|o4$|gpt-5)/

  return !reasoningModelPattern.test(modelName)
}

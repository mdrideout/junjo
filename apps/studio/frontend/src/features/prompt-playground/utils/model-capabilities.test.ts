import { describe, it, expect } from 'vitest'
import { supportsTemperature } from './model-capabilities'

describe('supportsTemperature', () => {
  describe('GPT-5 models', () => {
    it('should return false for gpt-5 models with provider prefix', () => {
      expect(supportsTemperature('openai/gpt-5')).toBe(false)
      expect(supportsTemperature('openai/gpt-5-nano')).toBe(false)
      expect(supportsTemperature('openai/gpt-5-mini')).toBe(false)
      expect(supportsTemperature('openai/gpt-5-codex')).toBe(false)
    })

    it('should return false for gpt-5 models without provider prefix', () => {
      expect(supportsTemperature('gpt-5')).toBe(false)
      expect(supportsTemperature('gpt-5-nano')).toBe(false)
      expect(supportsTemperature('gpt-5-mini')).toBe(false)
    })
  })

  describe('o1 models', () => {
    it('should return false for o1 models with provider prefix', () => {
      expect(supportsTemperature('openai/o1-preview')).toBe(false)
      expect(supportsTemperature('openai/o1')).toBe(false)
      expect(supportsTemperature('openai/o1-mini')).toBe(false)
    })

    it('should return false for o1 models without provider prefix', () => {
      expect(supportsTemperature('o1-preview')).toBe(false)
      expect(supportsTemperature('o1')).toBe(false)
      expect(supportsTemperature('o1-mini')).toBe(false)
    })
  })

  describe('o3 models', () => {
    it('should return false for o3 models with provider prefix', () => {
      expect(supportsTemperature('openai/o3')).toBe(false)
      expect(supportsTemperature('openai/o3-mini')).toBe(false)
    })

    it('should return false for o3 models without provider prefix', () => {
      expect(supportsTemperature('o3')).toBe(false)
      expect(supportsTemperature('o3-mini')).toBe(false)
    })
  })

  describe('o4 models', () => {
    it('should return false for o4 models with provider prefix', () => {
      expect(supportsTemperature('openai/o4')).toBe(false)
      expect(supportsTemperature('openai/o4-preview')).toBe(false)
    })

    it('should return false for o4 models without provider prefix', () => {
      expect(supportsTemperature('o4')).toBe(false)
      expect(supportsTemperature('o4-preview')).toBe(false)
    })
  })

  describe('standard models (non-reasoning)', () => {
    it('should return true for GPT-4 models', () => {
      expect(supportsTemperature('openai/gpt-4')).toBe(true)
      expect(supportsTemperature('openai/gpt-4o')).toBe(true)
      expect(supportsTemperature('openai/gpt-4-turbo')).toBe(true)
      expect(supportsTemperature('gpt-4')).toBe(true)
    })

    it('should return true for GPT-3.5 models', () => {
      expect(supportsTemperature('openai/gpt-3.5-turbo')).toBe(true)
      expect(supportsTemperature('gpt-3.5-turbo')).toBe(true)
    })

    it('should return true for Claude models', () => {
      expect(supportsTemperature('anthropic/claude-3-5-sonnet-20241022')).toBe(true)
      expect(supportsTemperature('anthropic/claude-3-opus-20240229')).toBe(true)
    })

    it('should return true for Gemini models', () => {
      expect(supportsTemperature('gemini/gemini-2.5-flash')).toBe(true)
      expect(supportsTemperature('gemini/gemini-2.0-flash-exp')).toBe(true)
    })
  })

  describe('edge cases', () => {
    it('should handle models that start with reasoning model names but are not', () => {
      // These should still return false because they match the pattern
      expect(supportsTemperature('openai/o1-something-else')).toBe(false)
      expect(supportsTemperature('openai/gpt-5-something')).toBe(false)
    })

    it('should handle empty or invalid model strings', () => {
      expect(supportsTemperature('')).toBe(true) // Empty string doesn't match pattern
      expect(supportsTemperature('/')).toBe(true) // Just a slash
    })
  })
})

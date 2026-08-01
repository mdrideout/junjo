import { describe, expect, it } from 'vitest'
import { expirationFromPreset } from './expiration-presets'

const NOW = new Date('2026-08-01T15:00:00.000Z')

describe('access token expiration presets', () => {
  it('defaults to a non-expiring token', () => {
    expect(expirationFromPreset('never', NOW)).toBeNull()
  })

  it('calculates the supported fixed expiration choices', () => {
    expect(expirationFromPreset('30-days', NOW)).toBe('2026-08-31T15:00:00.000Z')
    expect(expirationFromPreset('90-days', NOW)).toBe('2026-10-30T15:00:00.000Z')
    expect(expirationFromPreset('1-year', NOW)).toBe('2027-08-01T15:00:00.000Z')
  })
})

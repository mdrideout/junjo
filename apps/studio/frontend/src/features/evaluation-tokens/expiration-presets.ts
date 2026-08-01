export const EXPIRATION_PRESETS = [
  { label: 'Does not expire', value: 'never' },
  { label: '30 days', value: '30-days' },
  { label: '90 days', value: '90-days' },
  { label: '1 year', value: '1-year' },
] as const

export type ExpirationPreset = (typeof EXPIRATION_PRESETS)[number]['value']

export function expirationFromPreset(
  preset: ExpirationPreset,
  now = new Date(),
): string | null {
  if (preset === 'never') return null

  const expiration = new Date(now)
  if (preset === '1-year') {
    expiration.setUTCFullYear(expiration.getUTCFullYear() + 1)
  } else {
    expiration.setUTCDate(expiration.getUTCDate() + (preset === '30-days' ? 30 : 90))
  }
  return expiration.toISOString()
}

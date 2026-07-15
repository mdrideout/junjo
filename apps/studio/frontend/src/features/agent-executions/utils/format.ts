export function formatNanoseconds(nanoseconds: number): string {
  if (nanoseconds < 1_000) return `${nanoseconds} ns`
  if (nanoseconds < 1_000_000) return `${(nanoseconds / 1_000).toFixed(1)} µs`
  if (nanoseconds < 1_000_000_000) return `${(nanoseconds / 1_000_000).toFixed(1)} ms`
  return `${(nanoseconds / 1_000_000_000).toFixed(2)} s`
}

export function shortIdentity(value: string): string {
  return value.length <= 14 ? value : `${value.slice(0, 6)}…${value.slice(-6)}`
}

export function formatUsageFieldName(value: string): string {
  return value.replace(/([a-z])([A-Z])/g, '$1 $2')
}

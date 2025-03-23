export function getSpanDurationString(start_time: string, end_time: string) {
  try {
    // Calculate the duration in microseconds using the new function
    const durationMicro = calculateDurationMicro(start_time, end_time)

    // Format the duration
    return formatDurationMicro(durationMicro)
  } catch (error) {
    console.error('Error calculating or formatting duration:', error)
    return 'Invalid Date'
  }
}

/**
 * Calculates the duration between two dates in microseconds.
 * @param startTime - The start date in ISO string format.
 * @param endTime - The end date in ISO string format.
 * @returns The duration in microseconds.
 * @throws Error if the date format is invalid.
 */
function calculateDurationMicro(startTime: string, endTime: string): number {
  const startMicro = getMicrosecondsSinceEpoch(startTime)
  const endMicro = getMicrosecondsSinceEpoch(endTime)
  return endMicro - startMicro
}

/**
 * Gets the number of microseconds since the epoch from an ISO string.
 * @param isoString - The ISO string to parse.
 * @returns The number of microseconds since the epoch.
 * @throws Error if the date format is invalid.
 */
function getMicrosecondsSinceEpoch(isoString: string) {
  const date = new Date(isoString)

  if (isNaN(date.getTime())) {
    throw new Error('Invalid Date format')
  }

  const microsecondPart = isoString.substring(isoString.indexOf('.') + 1, isoString.length - 1)
  const microseconds = parseInt(microsecondPart, 10) || 0 // Default to 0 if no fractional seconds

  return date.getTime() * 1000 + microseconds * 10 ** (6 - microsecondPart.length)
}

/**
 * Formats a duration in microseconds into a human-readable string.
 * @param durationMicro - The duration in microseconds.
 * @returns A formatted string representing the duration.
 */
function formatDurationMicro(durationMicro: number): string {
  const oneMilli = 1_000
  const oneSecond = 1_000_000

  if (durationMicro < oneMilli) {
    return `${durationMicro.toFixed(0)}µs`
  } else if (durationMicro < oneSecond) {
    const durationMilli = durationMicro / oneMilli
    const formattedMs = durationMilli.toFixed(1)
    return formattedMs.endsWith('.0') ? `${formattedMs.slice(0, -2)}ms` : `${formattedMs}ms`
  } else {
    const durationSeconds = durationMicro / oneSecond
    const formattedSeconds = durationSeconds.toFixed(3)
    return formattedSeconds.endsWith('.000') ? `${formattedSeconds.slice(0, -4)}s` : `${formattedSeconds}s`
  }
}

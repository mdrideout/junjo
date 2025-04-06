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
  const startMicro = isoStringToMicrosecondsSinceEpoch(startTime)
  const endMicro = isoStringToMicrosecondsSinceEpoch(endTime)
  return endMicro - startMicro
}

/**
 * Gets the number of microseconds since the epoch from an ISO string.
 * @param isoString - The ISO string to parse.
 * @returns The number of microseconds since the epoch.
 * @throws Error if the date format is invalid.
 */
export function isoStringToMicrosecondsSinceEpoch(isoString: string) {
  const date = new Date(isoString)
  if (isNaN(date.getTime())) {
    throw new Error('Invalid Date format')
  }

  // Split the ISO string on the decimal point
  const [_secondsPart, fractionPartWithZone] = isoString.split('.')
  if (!fractionPartWithZone) {
    return date.getTime() * 1000 // no fractional part
  }

  // Remove the timezone (assuming 'Z' or an offset) from the fraction
  const fractionPart = fractionPartWithZone.replace(/[^0-9]/g, '')

  // Pad the fraction to 6 digits (microseconds)
  const fractionPadded = fractionPart.padEnd(6, '0')
  const totalFractionMicro = parseInt(fractionPadded, 10)

  // Get milliseconds already included in date.getTime() and convert to microseconds.
  const msFraction = date.getTime() % 1000
  const msFractionMicro = msFraction * 1000

  // Compute only the remainder (the microseconds beyond the ms precision)
  const extraMicro = totalFractionMicro - msFractionMicro
  return date.getTime() * 1000 + extraMicro
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
    const formattedMs = durationMilli.toFixed(2)
    return formattedMs.endsWith('.0') ? `${formattedMs.slice(0, -2)}ms` : `${formattedMs}ms`
  } else {
    const durationSeconds = durationMicro / oneSecond
    const formattedSeconds = durationSeconds.toFixed(3)
    return formattedSeconds.endsWith('.000') ? `${formattedSeconds.slice(0, -4)}s` : `${formattedSeconds}s`
  }
}

/**
 * Nanoseconds to Microseconds
 */
export function nanoSecondsToMicrosecons(nanoseconds: number): number {
  return nanoseconds / 1000
}

/**
 * Formats microseconds since the epoch into a HH:MM:SS.ffffff string (UTC).
 *
 * The time is always calculated based on the UTC timezone.
 *
 * @param microsecondsSinceEpoch - The total number of microseconds since 1970-01-01T00:00:00Z.
 * Should be a standard JavaScript number (or BigInt if needed, though number is usually sufficient).
 * @returns A string formatted as HH:MM:SS.ffffff in UTC.
 * @throws Error if the input is not a finite number or results in an invalid Date.
 */
export function formatMicrosecondsSinceEpochToTime(microsecondsSinceEpoch: number): string {
  // Validate input
  if (typeof microsecondsSinceEpoch !== 'number' || !Number.isFinite(microsecondsSinceEpoch)) {
    throw new Error('Input must be a finite number representing microseconds since epoch.')
  }

  // Calculate milliseconds since epoch for the Date object
  // Math.floor handles potential negative numbers correctly for epoch conversion
  const millisecondsSinceEpoch = Math.floor(microsecondsSinceEpoch / 1000)

  // Calculate the microsecond fraction part (0-999999)
  // Use Math.abs before modulo to handle negative epoch times correctly, ensuring a positive fraction.
  // Although epoch times are usually positive, this makes the function more robust.
  const microsecondFraction = Math.abs(microsecondsSinceEpoch) % 1000000

  // Create a Date object using the milliseconds
  const date = new Date(millisecondsSinceEpoch)

  // Check if the resulting date is valid
  if (isNaN(date.getTime())) {
    throw new Error('Invalid microsecond value resulted in an invalid Date.')
  }

  // Extract UTC time components
  const hours = date.getUTCHours()
  const minutes = date.getUTCMinutes()
  const seconds = date.getUTCSeconds()

  // Format components with leading zeros if needed
  const formattedHours = String(hours).padStart(2, '0')
  const formattedMinutes = String(minutes).padStart(2, '0')
  const formattedSeconds = String(seconds).padStart(2, '0')

  // Format the microsecond fraction with leading zeros to 6 digits
  // Ensure it's an integer before padding
  const formattedMicroseconds = String(Math.floor(microsecondFraction)).padStart(6, '0')

  // Combine into the final string
  return `${formattedHours}:${formattedMinutes}:${formattedSeconds}.${formattedMicroseconds}`
}

export function getSpanDurationString(start_time: string, end_time: string) {
  const startTime = new Date(start_time)
  const endTime = new Date(end_time)

  // Check if the date strings are valid
  if (isNaN(startTime.getTime()) || isNaN(endTime.getTime())) {
    console.error('Invalid date strings provided:', start_time, end_time)
    return 'Invalid Date'
  }

  // Calculate the duration in microseconds
  const durationMicro = calculateDurationMicro(startTime, endTime)

  // Format the duration
  return formatDurationMicro(durationMicro)
}

/**
 * Calculates the duration between two dates in microseconds.
 * @param startTime - The start date.
 * @param endTime - The end date.
 * @returns The duration in microseconds.
 */
function calculateDurationMicro(startTime: Date, endTime: Date): number {
  // Convert to microseconds
  const startMicro = startTime.getTime() * 1000 // Convert milliseconds to microseconds
  const endMicro = endTime.getTime() * 1000 // Convert milliseconds to microseconds

  // Extract the fractional part of the milliseconds (microseconds)
  const startFractionalMicro = startTime.getMilliseconds() * 1000
  const endFractionalMicro = endTime.getMilliseconds() * 1000

  // Calculate the total microseconds
  const totalStartMicro = startMicro + startFractionalMicro
  const totalEndMicro = endMicro + endFractionalMicro

  return totalEndMicro - totalStartMicro
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
    return `${durationMicro.toFixed(0)} µs`
  } else if (durationMicro < oneSecond) {
    const durationMilli = durationMicro / oneMilli
    const formattedMs = durationMilli.toFixed(1)
    return formattedMs.endsWith('.0') ? `${formattedMs.slice(0, -2)} ms` : `${formattedMs} ms`
  } else {
    const durationSeconds = durationMicro / oneSecond
    const formattedSeconds = durationSeconds.toFixed(3)
    return formattedSeconds.endsWith('.000') ? `${formattedSeconds.slice(0, -4)} s` : `${formattedSeconds} s`
  }
}

export function getSpanDurationString(start_time: string, end_time: string) {
  const startTime = new Date(start_time)
  const endTime = new Date(end_time)
  const duration = endTime.getTime() - startTime.getTime()

  // Format
  if (duration < 1000) {
    return `${duration}ms`
  } else {
    const durationSeconds = duration / 1000
    return `${durationSeconds.toFixed(2)}s`
  }
}

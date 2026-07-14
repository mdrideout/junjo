export const formatDateForChat = (date: Date): string => {
  const month = date.toLocaleString('default', { month: 'short' })
  const day = date.getDate()
  let hours = date.getHours()
  const minutes = date.getMinutes().toString().padStart(2, '0')
  const ampm = hours >= 12 ? 'pm' : 'am'
  hours %= 12
  hours = hours || 12
  return `${month} ${day}, ${hours}:${minutes}${ampm}`
}

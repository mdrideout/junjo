/**
 * Decode a base64-encoded JSON string
 * @param base64Str
 * @returns
 */
export function decodeBase64Json(base64Str: string): any {
  try {
    const jsonStr = atob(base64Str)
    return JSON.parse(jsonStr)
  } catch (error) {
    console.error('Failed to decode base64 JSON:', error)
    return null
  }
}

// ...existing code...
import { z } from 'zod'
import { jwtDecode } from 'jwt-decode'

const DecodedTokenSchema = z.object({
  email: z.string().email(),
  exp: z.number(), // expires at
  iat: z.number(), // issued at
})

export type DecodedToken = z.infer<typeof DecodedTokenSchema>

/**
 * Decode and validate a JWT token
 * @param tokenStr
 * @returns
 */
export function decodeAndValidateToken(tokenStr: string): DecodedToken | null {
  try {
    const decoded = jwtDecode(tokenStr)
    const result = DecodedTokenSchema.safeParse(decoded)
    return result.success ? result.data : null
  } catch {
    return null
  }
}

/**
 * Is the token expired?
 *
 * This function will return true if the token is expired or if the token is invalid.
 * @param tokenStr
 * @returns
 */
export function isTokenExpired(tokenStr: string) {
  const decoded = decodeAndValidateToken(tokenStr)
  if (!decoded) return true

  // Check exp
  return decoded.exp * 1000 < Date.now()
}

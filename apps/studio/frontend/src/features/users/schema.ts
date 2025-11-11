import { z } from 'zod'
import { utcDatetimeSchema } from '../../lib/datetime-utils'

/**
 * Schema for an individual user object.
 *
 * Matches backend Pydantic schema in:
 * backend/app/db_sqlite/users/schemas.py (UserRead)
 */
export const userSchema = z.object({
  id: z.string(),
  email: z.string().email(),
  is_active: z.boolean(),
  created_at: utcDatetimeSchema, // Always UTC with 'Z' suffix from backend
  updated_at: utcDatetimeSchema, // Always UTC with 'Z' suffix from backend
})

// Schema for the API response containing a list of users
export const ListUsersResponseSchema = z.array(userSchema)

// Type aliases for better readability
export type User = z.infer<typeof userSchema>
export type ListUsersResponse = z.infer<typeof ListUsersResponseSchema>

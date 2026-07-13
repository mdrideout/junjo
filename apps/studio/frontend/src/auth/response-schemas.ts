import { z } from 'zod'

/**
 * Response schema for user mutation operations.
 *
 * Used by:
 * - POST /users/create-first-user
 * - POST /sign-in
 * - POST /sign-out
 * - POST /users (create user)
 * - DELETE /users/{user_id}
 *
 * Matches backend Pydantic schema:
 * backend/app/db_sqlite/users/schemas.py (UserResponse)
 */
export const UserResponseSchema = z.object({
  message: z.string(),
})

export type UserResponse = z.infer<typeof UserResponseSchema>

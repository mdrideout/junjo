import { z } from 'zod'

/**
 * Response schema for user mutation operations.
 *
 * Used by:
 * - POST /api/v1/users/create-first-user
 * - POST /api/v1/sign-in
 * - POST /api/v1/sign-out
 * - POST /api/v1/users (create user)
 * - DELETE /api/v1/users/{user_id}
 * - POST /api/v1/cli-sign-ins/{user_code}/deny
 *
 * Matches the backend response type:
 * backend/server/src/features/auth/mod.rs (UserResponse)
 */
export const UserResponseSchema = z.object({
  message: z.string(),
})

export type UserResponse = z.infer<typeof UserResponseSchema>

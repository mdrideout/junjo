import { z } from 'zod'

// Zod schema for User
export const UserSchema = z.object({
  email: z.string().email(),
  password: z.string().min(1),
})
export type User = z.infer<typeof UserSchema>

// Zod schema for User Database
export const UserDatabaseSchema = z.array(UserSchema)
export type UserDatabase = z.infer<typeof UserDatabaseSchema>

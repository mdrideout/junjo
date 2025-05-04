import { z } from 'zod'

// Schema for an individual user object
export const userSchema = z.object({
  ID: z.number().int(),
  Email: z.string(),
  CreatedAt: z.string().datetime(), // Or z.coerce.date() if you want to parse it into a Date object
})

// Schema for the API response containing a list of users
export const ListUsersResponseSchema = z.array(userSchema)

// Optional: Define a type alias for better readability if needed elsewhere
export type User = z.infer<typeof userSchema>
export type ListUsersResponse = z.infer<typeof ListUsersResponseSchema>

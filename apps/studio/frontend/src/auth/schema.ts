import { z } from 'zod'

export const UsersExistSchema = z.object({
  usersExist: z.boolean(),
})
export type UsersExist = z.infer<typeof UsersExistSchema>

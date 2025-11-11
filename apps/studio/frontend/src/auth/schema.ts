import { z } from 'zod'

export const UsersExistSchema = z.object({
  users_exist: z.boolean(),
})
export type UsersExist = z.infer<typeof UsersExistSchema>

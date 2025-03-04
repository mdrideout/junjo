import { z } from 'zod'
import { zodHandlePythonDatetime } from '../../util/zod-utils'
import { ChatWithMembersReadSchema } from '../chat/schemas'

// Native enum for GenderEnum
export enum GenderEnum {
  MALE = 'MALE',
  FEMALE = 'FEMALE',
}

// Zod schema for ContactRead
export const ContactReadSchema = z.object({
  id: z.string(),
  created_at: zodHandlePythonDatetime('created_at'),
  updated_at: zodHandlePythonDatetime('updated_at'),
  gender: z.nativeEnum(GenderEnum),
  first_name: z.string(),
  last_name: z.string(),
  age: z.number().int(),
  weight_lbs: z.number(),
  us_state: z.string(),
  city: z.string(),
  bio: z.string(),
})
export type ContactRead = z.infer<typeof ContactReadSchema>

export const CreateSetupContactResponseSchema = z.object({
  contact: ContactReadSchema,
  chat_with_members: ChatWithMembersReadSchema,
})
export type CreateSetupContactResponse = z.infer<typeof CreateSetupContactResponseSchema>

import { z } from 'zod'
import { zodHandlePythonDatetime } from '../../util/zod-utils'
import { ChatWithMembersReadSchema } from '../chat/schemas'

// Native enum for Sex
export enum Sex {
  MALE = 'MALE',
  FEMALE = 'FEMALE',
  OTHER = 'OTHER',
}

// Zod schema for ContactRead
export const ContactReadSchema = z.object({
  id: z.string(),
  created_at: zodHandlePythonDatetime('created_at'),
  updated_at: zodHandlePythonDatetime('updated_at'),
  avatar_id: z.string(),
  sex: z.nativeEnum(Sex),
  first_name: z.string(),
  last_name: z.string(),
  age: z.number().int(),
  openness: z.number(),
  conscientiousness: z.number(),
  neuroticism: z.number(),
  agreeableness: z.number(),
  extraversion: z.number(),
  intelligence: z.number(),
  religiousness: z.number(),
  attractiveness: z.number(),
  trauma: z.number(),
  latitude: z.number(),
  longitude: z.number(),
  city: z.string(),
  state: z.string(),
  bio: z.string(),
})
export type ContactRead = z.infer<typeof ContactReadSchema>

export const CreateSetupContactResponseSchema = z.object({
  contact: ContactReadSchema,
  chat_with_members: ChatWithMembersReadSchema,
})
export type CreateSetupContactResponse = z.infer<typeof CreateSetupContactResponseSchema>

import { z } from 'zod'

// Native enum for GenderEnum
export enum GenderEnum {
  MALE = 'MALE',
  FEMALE = 'FEMALE',
}

// Zod schema for ContactRead
export const ContactReadSchema = z.object({
  id: z.string(),
  created_at: z
    .string()
    .refine(
      (val) => {
        // Check if the string matches the expected format YYYY-MM-DDTHH:mm:ss
        return /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$/.test(val)
      },
      {
        message: 'Invalid date format. Expected YYYY-MM-DDTHH:mm:ss',
      }
    )
    .transform((val) => new Date(val)), // Convert to Date object
  updated_at: z
    .string()
    .refine(
      (val) => {
        // Check if the string matches the expected format YYYY-MM-DDTHH:mm:ss
        return /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$/.test(val)
      },
      {
        message: 'Invalid date format. Expected YYYY-MM-DDTHH:mm:ss',
      }
    )
    .transform((val) => new Date(val)), // Convert to Date object
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

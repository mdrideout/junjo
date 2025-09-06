import { z } from 'zod'
import { zodHandlePythonDatetime } from '../../util/zod-utils' // Adjust path as needed

export const MessageReadSchema = z.object({
  id: z.string(),
  created_at: zodHandlePythonDatetime('created_at'),
  contact_id: z.string().nullable(),
  chat_id: z.string(),
  message: z.string(),
  image_id: z.string().nullable(),
})

export type MessageRead = z.infer<typeof MessageReadSchema>

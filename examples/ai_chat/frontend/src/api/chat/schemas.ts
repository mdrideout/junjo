import { z } from 'zod'
import { zodHandlePythonDatetime } from '../../util/zod-utils'

// Zod schema for ChatRead
export const ChatReadSchema = z.object({
  id: z.string(),
  created_at: zodHandlePythonDatetime('created_at'),
  last_message_time: zodHandlePythonDatetime('last_message_time'),
})

export type ChatRead = z.infer<typeof ChatReadSchema>

// Zod schema for ChatMemberRead
export const ChatMemberReadSchema = z.object({
  joined_at: zodHandlePythonDatetime('joined_at'),
  contact_id: z.string(),
})

export type ChatMemberRead = z.infer<typeof ChatMemberReadSchema>

// Zod schema for ChatWithMembersRead
export const ChatWithMembersReadSchema = ChatReadSchema.extend({
  members: z.array(ChatMemberReadSchema),
})

export type ChatWithMembersRead = z.infer<typeof ChatWithMembersReadSchema>

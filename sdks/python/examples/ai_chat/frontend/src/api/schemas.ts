import { z } from 'zod'

const NonEmptyTextSchema = z.string().min(1)
const IdentifierSchema = z.string().min(1)
export const MAX_TURN_TEXT_LENGTH = 2500

export const AgentErrorResponseSchema = z
  .object({
    detail: NonEmptyTextSchema,
    agent_run_id: IdentifierSchema,
    termination_reason: NonEmptyTextSchema,
  })
  .strict()
export type AgentErrorResponse = z.infer<typeof AgentErrorResponseSchema>

export const ConversationSchema = z
  .object({
    id: IdentifierSchema,
    title: NonEmptyTextSchema,
  })
  .strict()
export type Conversation = z.infer<typeof ConversationSchema>

export const ConversationsResponseSchema = z
  .object({
    conversations: z.array(ConversationSchema),
  })
  .strict()
export type ConversationsResponse = z.infer<typeof ConversationsResponseSchema>

export const MessageSchema = z
  .object({
    id: IdentifierSchema,
    turn_id: IdentifierSchema,
    role: z.enum(['user', 'assistant']),
    content: NonEmptyTextSchema,
    image_url: z.string().min(1).nullable(),
    image_alt: z.string().min(1).nullable(),
    created_at: z.string().datetime({ offset: true }),
  })
  .strict()
  .superRefine((message, context) => {
    if ((message.image_url === null) !== (message.image_alt === null)) {
      context.addIssue({
        code: z.ZodIssueCode.custom,
        message: 'image_url and image_alt must both be present or both be null',
        path: ['image_alt'],
      })
    }
  })
export type Message = z.infer<typeof MessageSchema>

export const MessagesResponseSchema = z
  .object({
    conversation_id: IdentifierSchema,
    messages: z.array(MessageSchema),
  })
  .strict()
export type MessagesResponse = z.infer<typeof MessagesResponseSchema>

export const CreateTurnRequestSchema = z
  .object({
    text: NonEmptyTextSchema.max(MAX_TURN_TEXT_LENGTH),
  })
  .strict()
export type CreateTurnRequest = z.infer<typeof CreateTurnRequestSchema>

export const TurnResponseSchema = z
  .object({
    conversation_id: IdentifierSchema,
    workflow_run_id: IdentifierSchema,
    agent_run_id: IdentifierSchema,
    user_message: MessageSchema,
    assistant_message: MessageSchema,
  })
  .strict()
  .superRefine((turn, context) => {
    if (turn.user_message.role !== 'user') {
      context.addIssue({
        code: z.ZodIssueCode.custom,
        message: 'user_message must have the user role',
        path: ['user_message', 'role'],
      })
    }
    if (turn.assistant_message.role !== 'assistant') {
      context.addIssue({
        code: z.ZodIssueCode.custom,
        message: 'assistant_message must have the assistant role',
        path: ['assistant_message', 'role'],
      })
    }
    if (turn.user_message.turn_id !== turn.assistant_message.turn_id) {
      context.addIssue({
        code: z.ZodIssueCode.custom,
        message: 'Returned messages must belong to the same turn',
        path: ['assistant_message', 'turn_id'],
      })
    }
  })
export type TurnResponse = z.infer<typeof TurnResponseSchema>

export interface TurnEvidence {
  workflowRunId: string
  agentRunId: string
}

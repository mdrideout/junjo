import { z } from 'zod'

const NonEmptyTextSchema = z.string().min(1)
const IdentifierSchema = z.string().min(1)
const TimestampSchema = z.string().datetime({ offset: true })
export const MAX_TURN_TEXT_LENGTH = 2500

export const ContactSexSchema = z.enum(['male', 'female'])
export type ContactSex = z.infer<typeof ContactSexSchema>

export const ContactSchema = z
  .object({
    id: IdentifierSchema,
    first_name: NonEmptyTextSchema,
    last_name: NonEmptyTextSchema,
    sex: ContactSexSchema,
    age: z.number().int().min(18).max(100),
    city: NonEmptyTextSchema,
    state: NonEmptyTextSchema,
    bio: NonEmptyTextSchema,
    avatar_url: NonEmptyTextSchema,
  })
  .strict()
export type Contact = z.infer<typeof ContactSchema>

export const ConversationSchema = z
  .object({
    id: IdentifierSchema,
    title: NonEmptyTextSchema,
    contact: ContactSchema,
    last_message_at: TimestampSchema.nullable(),
  })
  .strict()
export type Conversation = z.infer<typeof ConversationSchema>

export const ConversationsResponseSchema = z
  .object({
    conversations: z.array(ConversationSchema),
  })
  .strict()
export type ConversationsResponse = z.infer<typeof ConversationsResponseSchema>

export const CreateContactRequestSchema = z
  .object({ sex: ContactSexSchema })
  .strict()
export type CreateContactRequest = z.infer<typeof CreateContactRequestSchema>

export const CreateContactResponseSchema = z
  .object({ conversation: ConversationSchema })
  .strict()
export type CreateContactResponse = z.infer<typeof CreateContactResponseSchema>

export const MessageSchema = z
  .object({
    id: IdentifierSchema,
    turn_id: IdentifierSchema,
    role: z.enum(['user', 'assistant']),
    content: NonEmptyTextSchema,
    image_url: z.string().min(1).nullable(),
    image_alt: z.string().min(1).nullable(),
    created_at: TimestampSchema,
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

export const ContextPolicySchema = z
  .object({
    id: z.literal('recent-completed-turns'),
    version: z.literal(1),
    recent_turn_limit: z.number().int().positive(),
  })
  .strict()
export type ContextPolicy = z.infer<typeof ContextPolicySchema>

export const ExecutionReferencesSchema = z
  .object({
    workflow_run_id: IdentifierSchema.nullable(),
    agent_run_id: IdentifierSchema.nullable(),
  })
  .strict()
export type ExecutionReferences = z.infer<typeof ExecutionReferencesSchema>

export const TurnFailureSchema = z
  .object({
    code: NonEmptyTextSchema,
    detail: NonEmptyTextSchema,
    termination_reason: NonEmptyTextSchema.nullable(),
  })
  .strict()
export type TurnFailure = z.infer<typeof TurnFailureSchema>

export const TurnSchema = z
  .object({
    object_type: z.literal('ai_chat.turn'),
    schema_version: z.literal(1),
    id: IdentifierSchema,
    revision: z.number().int().nonnegative(),
    conversation_id: IdentifierSchema,
    sequence: z.number().int().positive(),
    status: z.enum(['admitted', 'running', 'completed', 'failed', 'cancelled']),
    context_policy: ContextPolicySchema,
    user_message: MessageSchema,
    assistant_message: MessageSchema.nullable(),
    execution_references: ExecutionReferencesSchema,
    failure: TurnFailureSchema.nullable(),
    created_at: TimestampSchema,
    updated_at: TimestampSchema,
    completed_at: TimestampSchema.nullable(),
  })
  .strict()
  .superRefine((turn, context) => {
    if (turn.user_message.role !== 'user' || turn.user_message.turn_id !== turn.id) {
      context.addIssue({
        code: z.ZodIssueCode.custom,
        message: 'user_message must be the user message for this turn',
        path: ['user_message'],
      })
    }
    if (
      turn.assistant_message !== null
      && (turn.assistant_message.role !== 'assistant' || turn.assistant_message.turn_id !== turn.id)
    ) {
      context.addIssue({
        code: z.ZodIssueCode.custom,
        message: 'assistant_message must be the assistant message for this turn',
        path: ['assistant_message'],
      })
    }
    const terminal = ['completed', 'failed', 'cancelled'].includes(turn.status)
    if (terminal !== (turn.completed_at !== null)) {
      context.addIssue({
        code: z.ZodIssueCode.custom,
        message: 'completed_at must be present exactly when the turn is terminal',
        path: ['completed_at'],
      })
    }
    if (turn.status === 'completed' && turn.assistant_message === null) {
      context.addIssue({
        code: z.ZodIssueCode.custom,
        message: 'completed turns require an assistant message',
        path: ['assistant_message'],
      })
    }
    const failed = turn.status === 'failed' || turn.status === 'cancelled'
    if (failed !== (turn.failure !== null)) {
      context.addIssue({
        code: z.ZodIssueCode.custom,
        message: 'failure must be present exactly when a turn failed or was cancelled',
        path: ['failure'],
      })
    }
  })
export type Turn = z.infer<typeof TurnSchema>

export const TurnListResponseSchema = z
  .object({
    conversation_id: IdentifierSchema,
    turns: z.array(TurnSchema),
  })
  .strict()
export type TurnListResponse = z.infer<typeof TurnListResponseSchema>

export const CreateTurnRequestSchema = z
  .object({
    text: NonEmptyTextSchema.max(MAX_TURN_TEXT_LENGTH),
  })
  .strict()
export type CreateTurnRequest = z.infer<typeof CreateTurnRequestSchema>

export const PublicConfigResponseSchema = z
  .object({
    debug_enabled: z.boolean(),
    studio_ui_url: z.string().url().nullable(),
    service_namespace: z.string(),
    service_name: NonEmptyTextSchema,
  })
  .strict()
  .superRefine((config, context) => {
    if (config.debug_enabled && config.studio_ui_url === null) {
      context.addIssue({
        code: z.ZodIssueCode.custom,
        message: 'studio_ui_url is required when debug mode is enabled',
        path: ['studio_ui_url'],
      })
    }
  })
export type PublicConfig = z.infer<typeof PublicConfigResponseSchema>

export const TurnProblemResponseSchema = z
  .object({
    type: NonEmptyTextSchema,
    title: NonEmptyTextSchema,
    status: z.number().int(),
    detail: NonEmptyTextSchema,
    instance: NonEmptyTextSchema,
    turn_id: IdentifierSchema.nullable().optional(),
    workflow_run_id: IdentifierSchema.nullable().optional(),
    agent_run_id: IdentifierSchema.nullable().optional(),
    termination_reason: NonEmptyTextSchema.nullable().optional(),
    turn: TurnSchema.nullable().optional(),
  })
  .strict()
export type TurnProblemResponse = z.infer<typeof TurnProblemResponseSchema>

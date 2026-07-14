import { z } from 'zod'
import {
  JsonValueSchema,
  NonEmptyPortableStringSchema,
  SafeNonNegativeIntegerSchema,
  SafePositiveIntegerSchema,
} from '../../telemetry-contract/schemas/scalars'

const FullPayloadEvidenceSchema = z
  .object({
    mode: z.literal('full'),
    policy: NonEmptyPortableStringSchema,
    value: JsonValueSchema,
    reference: z.null(),
    reason: z.null(),
  })
  .strict()

const RedactedPayloadEvidenceSchema = z
  .object({
    mode: z.literal('redacted'),
    policy: NonEmptyPortableStringSchema,
    value: JsonValueSchema,
    reference: z.null(),
    reason: z.null(),
  })
  .strict()

const ExcludedPayloadEvidenceSchema = z
  .object({
    mode: z.literal('excluded'),
    policy: NonEmptyPortableStringSchema,
    value: z.null(),
    reference: z.null(),
    reason: z.null(),
  })
  .strict()

const ReferencedPayloadEvidenceSchema = z
  .object({
    mode: z.literal('reference'),
    policy: NonEmptyPortableStringSchema,
    value: z.null(),
    reference: NonEmptyPortableStringSchema,
    reason: z.null(),
  })
  .strict()

const MissingPayloadEvidenceSchema = z
  .object({
    mode: z.literal('missing'),
    policy: z.null(),
    value: z.null(),
    reference: z.null(),
    reason: NonEmptyPortableStringSchema,
  })
  .strict()

export const PayloadEvidenceSchema = z.discriminatedUnion('mode', [
  FullPayloadEvidenceSchema,
  RedactedPayloadEvidenceSchema,
  ExcludedPayloadEvidenceSchema,
  ReferencedPayloadEvidenceSchema,
  MissingPayloadEvidenceSchema,
])
export type PayloadEvidence = z.infer<typeof PayloadEvidenceSchema>

export const StoreTransitionSchema = z
  .object({
    sequence: SafePositiveIntegerSchema,
    revision_before: SafeNonNegativeIntegerSchema,
    revision_after: SafeNonNegativeIntegerSchema,
    span_id: z.string().regex(/^[0-9a-f]{16}$/),
    event_id: NonEmptyPortableStringSchema,
    action: NonEmptyPortableStringSchema,
    patch: PayloadEvidenceSchema,
    before: JsonValueSchema.nullable(),
    after: JsonValueSchema.nullable(),
  })
  .strict()
  .superRefine((transition, context) => {
    if (![transition.revision_before, transition.revision_before + 1].includes(transition.revision_after)) {
      context.addIssue({
        code: z.ZodIssueCode.custom,
        message: 'Transition revision must stay equal or increment by one',
        path: ['revision_after'],
      })
    }
  })
export type StoreTransition = z.infer<typeof StoreTransitionSchema>

export const StoreDetailSchema = z
  .object({
    available: z.boolean(),
    store_id: NonEmptyPortableStringSchema.nullable(),
    revision_start: SafeNonNegativeIntegerSchema.nullable(),
    revision_end: SafeNonNegativeIntegerSchema.nullable(),
    transition_count: SafeNonNegativeIntegerSchema,
    reconstructable_claimed: z.boolean(),
    reconstructable: z.boolean(),
    reconstruction_status: z.enum(['verified', 'policy_unavailable', 'failed', 'not_applicable']),
    reconstruction_reason: NonEmptyPortableStringSchema.nullable(),
    start: PayloadEvidenceSchema.nullable(),
    end: PayloadEvidenceSchema.nullable(),
    transitions: z.array(StoreTransitionSchema),
  })
  .strict()
  .superRefine((state, context) => {
    if (!state.available) {
      const hasEvidence = [state.store_id, state.revision_start, state.revision_end, state.start, state.end]
        .some((value) => value !== null)
      if (
        hasEvidence ||
        state.transition_count !== 0 ||
        state.reconstructable_claimed ||
        state.reconstructable ||
        state.transitions.length > 0
      ) {
        context.addIssue({
          code: z.ZodIssueCode.custom,
          message: 'Unavailable Store cannot contain Store or reconstruction evidence',
        })
      }
      if (state.reconstruction_status !== 'not_applicable' || state.reconstruction_reason === null) {
        context.addIssue({
          code: z.ZodIssueCode.custom,
          message: 'Unavailable Store requires a not-applicable reconstruction reason',
        })
      }
      return
    }

    if (state.reconstructable) {
      if (
        state.store_id === null ||
        state.revision_start === null ||
        state.revision_end === null ||
        state.start === null ||
        state.end === null ||
        state.transition_count !== state.transitions.length
      ) {
        context.addIssue({
          code: z.ZodIssueCode.custom,
          message: 'Verified reconstruction requires complete Store evidence and every transition',
        })
      }
    }
    if (state.reconstruction_status === 'verified' && !state.reconstructable) {
      context.addIssue({
        code: z.ZodIssueCode.custom,
        message: 'Verified status requires reconstructability',
        path: ['reconstruction_status'],
      })
    }
    if (state.reconstructable && state.reconstruction_status !== 'verified') {
      context.addIssue({
        code: z.ZodIssueCode.custom,
        message: 'Reconstructable Store requires verified status',
        path: ['reconstruction_status'],
      })
    }
    if (state.reconstruction_status === 'not_applicable') {
      context.addIssue({
        code: z.ZodIssueCode.custom,
        message: 'Available Store cannot be not-applicable',
        path: ['reconstruction_status'],
      })
    }
    if (
      (state.reconstruction_status === 'verified' && state.reconstruction_reason !== null) ||
      (state.reconstruction_status !== 'verified' && state.reconstruction_reason === null)
    ) {
      context.addIssue({
        code: z.ZodIssueCode.custom,
        message: 'Reconstruction status and reason are inconsistent',
        path: ['reconstruction_reason'],
      })
    }
  })
export type StoreDetail = z.infer<typeof StoreDetailSchema>

export const EvidenceDiagnosticSchema = z
  .object({
    code: NonEmptyPortableStringSchema,
    path: NonEmptyPortableStringSchema,
    message: NonEmptyPortableStringSchema,
  })
  .strict()
export type EvidenceDiagnostic = z.infer<typeof EvidenceDiagnosticSchema>

export const EvidenceIntegritySchema = z
  .object({
    status: z.enum(['complete', 'partial']),
    diagnostics: z.array(EvidenceDiagnosticSchema),
    loss_counts: z
      .object({
        resource_dropped_attributes: SafeNonNegativeIntegerSchema,
        span_dropped_attributes: SafeNonNegativeIntegerSchema,
        span_dropped_events: SafeNonNegativeIntegerSchema,
        span_dropped_links: SafeNonNegativeIntegerSchema,
        event_dropped_attributes: SafeNonNegativeIntegerSchema,
      })
      .strict(),
  })
  .strict()
  .superRefine((integrity, context) => {
    const hasLoss = Object.values(integrity.loss_counts).some((count) => count > 0)
    const expectedStatus = integrity.diagnostics.length > 0 || hasLoss ? 'partial' : 'complete'
    if (integrity.status !== expectedStatus) {
      context.addIssue({
        code: z.ZodIssueCode.custom,
        message: 'Integrity status does not match diagnostics and loss counters',
        path: ['status'],
      })
    }
  })
export type EvidenceIntegrity = z.infer<typeof EvidenceIntegritySchema>

import { z } from 'zod'
import { utcDatetimeSchema } from '../../util/datetime-utils'
import { EvaluationTokenScopeSchema } from '../evaluation-tokens/schemas'

/**
 * A pending CLI sign-in, as the approval page shows it.
 *
 * `client_name` is text the requesting terminal chose. Studio has not
 * verified it.
 */
export const CliSignInReadSchema = z
  .object({
    user_code: z.string().min(1),
    client_name: z.string().min(1),
    scopes: z.array(EvaluationTokenScopeSchema).min(1),
    expires_at: utcDatetimeSchema,
  })
  .strict()
export type CliSignInRead = z.infer<typeof CliSignInReadSchema>

/** The developer access token that approving a CLI sign-in minted. */
export const CliSignInApprovedSchema = z
  .object({
    token_id: z.string().min(1),
    token_name: z.string().min(1),
  })
  .strict()
export type CliSignInApproved = z.infer<typeof CliSignInApprovedSchema>

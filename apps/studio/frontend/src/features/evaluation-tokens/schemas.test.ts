import { describe, expect, it } from 'vitest'
import {
  EvaluationTokenCreatedSchema,
  EvaluationTokenListSchema,
} from './schemas'

const TOKEN = {
  id: 'token-1',
  name: 'Coding agent',
  prefix: 'junjo_eval_abcd1234EFGH',
  scopes: ['evaluation:read', 'evaluation:write', 'evidence:read'],
  expires_at: null,
  revoked_at: null,
  created_by_user_id: 'user-1',
  created_at: '2026-07-27T22:00:00Z',
}

describe('evaluation token schemas', () => {
  it('keeps token secrets exclusive to the create response', () => {
    const created = EvaluationTokenCreatedSchema.parse({
      ...TOKEN,
      token:
        'junjo_eval_abcd1234EFGH.abcdefghijklmnopqrstuvwxyzABCDEFGH_12345678',
    })
    const listed = EvaluationTokenListSchema.parse({
      items: [TOKEN],
      next_cursor: null,
    })

    expect(created.token).toContain('.')
    expect(listed.items[0]).not.toHaveProperty('token')
  })

  it('rejects ingestion-style or unknown scopes', () => {
    expect(() =>
      EvaluationTokenListSchema.parse({
        items: [{ ...TOKEN, scopes: ['ingestion:write'] }],
        next_cursor: null,
      }),
    ).toThrow()
  })
})

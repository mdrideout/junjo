import { describe, expect, it } from 'vitest'
import { EvaluationTokenListSchema } from './schemas'

const TOKEN = {
  id: 'token-1',
  name: 'Coding agent',
  token:
    'jcli_0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ_-',
  scopes: ['evaluation:read', 'evaluation:write', 'evidence:read'],
  expires_at: null,
  created_by_user_id: 'user-1',
  created_at: '2026-07-27T22:00:00Z',
}

describe('evaluation token schemas', () => {
  it('keeps token secrets available in authenticated list responses', () => {
    const listed = EvaluationTokenListSchema.parse({
      items: [TOKEN],
      next_cursor: null,
    })

    expect(listed.items[0].token).toBe(TOKEN.token)
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

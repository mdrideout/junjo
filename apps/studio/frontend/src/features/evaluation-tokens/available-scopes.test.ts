import { describe, expect, it } from 'vitest'
import { AVAILABLE_SCOPES } from './available-scopes'
import { EvaluationTokenScopeSchema } from './schemas'

describe('developer access token scope descriptions', () => {
  it('describes every scope a token can hold, once each', () => {
    expect(AVAILABLE_SCOPES.map((scope) => scope.value)).toEqual(
      EvaluationTokenScopeSchema.options,
    )
  })
})

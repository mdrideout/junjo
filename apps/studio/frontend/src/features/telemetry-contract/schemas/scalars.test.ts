import { describe, expect, it } from 'vitest'

import { JsonValueSchema } from './scalars'

function nestedArrays(depth: number): unknown {
  let value: unknown = null
  for (let index = 0; index < depth; index += 1) value = [value]
  return value
}

describe('portable JSON scalar contracts', () => {
  it('accepts nesting depth 128 and rejects 129', () => {
    expect(JsonValueSchema.safeParse(nestedArrays(128)).success).toBe(true)
    expect(JsonValueSchema.safeParse(nestedArrays(129)).success).toBe(false)
  })

  it('rejects extreme nesting iteratively instead of overflowing the process stack', () => {
    const parse = () => JsonValueSchema.safeParse(nestedArrays(10_000))

    expect(parse).not.toThrow()
    expect(parse().success).toBe(false)
  })
})

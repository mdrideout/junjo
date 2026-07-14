import { describe, expect, it } from 'vitest'
import {
  compareNanosecondTimestamps,
  nanosecondsBeforeMicroseconds,
  nanosecondsStringToMicroseconds,
} from './duration-utils'

describe('exact OTLP nanosecond timestamps', () => {
  it('orders adjacent timestamps above the JavaScript safe-integer boundary', () => {
    const left = '9007199254740992'
    const right = '9007199254740993'

    expect(Number(left)).toBe(Number(right))
    expect(compareNanosecondTimestamps(left, right)).toBe(-1)
    expect(compareNanosecondTimestamps(right, left)).toBe(1)
  })

  it('truncates only when converting exact nanoseconds to display microseconds', () => {
    expect(nanosecondsStringToMicroseconds('1700000000123456789')).toBe(1700000000123456)
  })

  it('compares exact nanoseconds to a microsecond boundary without Number coercion', () => {
    const boundary = 1_700_000_000_123_457

    expect(nanosecondsBeforeMicroseconds('1700000000123456999', boundary)).toBe(true)
    expect(nanosecondsBeforeMicroseconds('1700000000123457000', boundary)).toBe(false)
  })

  it('rejects a display conversion that would exceed the safe-integer domain', () => {
    expect(() => nanosecondsStringToMicroseconds('18446744073709551615')).toThrow(
      'cannot be represented as safe epoch microseconds',
    )
  })
})

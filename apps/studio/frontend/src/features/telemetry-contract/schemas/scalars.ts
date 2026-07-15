import { z } from 'zod'

function isUnicodeScalarString(value: string): boolean {
  for (let index = 0; index < value.length; index += 1) {
    const codeUnit = value.charCodeAt(index)
    if (codeUnit >= 0xd800 && codeUnit <= 0xdbff) {
      const next = value.charCodeAt(index + 1)
      if (!(next >= 0xdc00 && next <= 0xdfff)) return false
      index += 1
    } else if (codeUnit >= 0xdc00 && codeUnit <= 0xdfff) {
      return false
    }
  }
  return true
}

export const PortableStringSchema = z.string().refine(isUnicodeScalarString, {
  message: 'Text must contain Unicode scalar values',
})

export const NonEmptyPortableStringSchema = z.string().min(1).refine(isUnicodeScalarString, {
  message: 'Text must contain Unicode scalar values',
})

export const SafeNonNegativeIntegerSchema = z
  .number()
  .int()
  .nonnegative()
  .refine(Number.isSafeInteger, { message: 'Integer must be in the safe JSON domain' })

export const SafePositiveIntegerSchema = z
  .number()
  .int()
  .positive()
  .refine(Number.isSafeInteger, { message: 'Integer must be in the safe JSON domain' })

const PortableJsonNumberSchema = z.number().finite().refine(
  (value) => !Number.isInteger(value) || Number.isSafeInteger(value),
  { message: 'JSON integers must remain inside the IEEE-754 safe integer domain' },
)

const MAX_JSON_NESTING_DEPTH = 128

type DepthItem = {
  value: unknown
  depth: number
  leave: boolean
}

function isWithinJsonDepthBound(value: unknown): boolean {
  const ancestors = new Set<object>()
  const pending: DepthItem[] = [{ value, depth: 0, leave: false }]
  while (pending.length > 0) {
    const current = pending.pop()
    if (current === undefined) break
    if (current.leave) {
      ancestors.delete(current.value as object)
      continue
    }
    if (current.depth > MAX_JSON_NESTING_DEPTH) return false
    if (current.value === null || typeof current.value !== 'object') continue
    if (ancestors.has(current.value)) return false
    ancestors.add(current.value)
    pending.push({ ...current, leave: true })
    if (Array.isArray(current.value)) {
      for (const item of current.value) {
        pending.push({ value: item, depth: current.depth + 1, leave: false })
      }
      continue
    }
    for (const [key, item] of Object.entries(current.value)) {
      pending.push({ value: key, depth: current.depth + 1, leave: false })
      pending.push({ value: item, depth: current.depth + 1, leave: false })
    }
  }
  return true
}

const RecursiveJsonValueSchema: z.ZodType<unknown> = z.lazy(() =>
  z.union([
    z.null(),
    z.boolean(),
    PortableJsonNumberSchema,
    PortableStringSchema,
    z.array(RecursiveJsonValueSchema),
    z.record(PortableStringSchema, RecursiveJsonValueSchema),
  ]),
)

export const JsonValueSchema: z.ZodType<unknown> = z
  .unknown()
  .refine(isWithinJsonDepthBound, {
    message: `JSON nesting must not exceed ${MAX_JSON_NESTING_DEPTH}`,
  })
  .pipe(RecursiveJsonValueSchema)

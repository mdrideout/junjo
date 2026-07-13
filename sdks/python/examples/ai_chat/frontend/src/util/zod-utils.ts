import { z } from 'zod'

// Helper function for validating and transforming date strings
export const zodHandlePythonDatetime = (fieldName: string) =>
  z
    .string()
    .refine((val) => /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$/.test(val), {
      message: `Invalid ${fieldName} format. Expected YYYY-MM-DDTHH:mm:ss`,
    })
    .transform((val) => new Date(val))

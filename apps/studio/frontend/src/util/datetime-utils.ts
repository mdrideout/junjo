/**
 * UTC datetime utilities for consistent timezone handling in the frontend.
 *
 * Pattern:
 * 1. Backend always sends ISO 8601 with 'Z' suffix (e.g., '2025-01-15T10:30:00Z')
 * 2. Frontend parses as Date objects (JavaScript Date is always UTC internally)
 * 3. Display using user's local timezone with Intl.DateTimeFormat
 * 4. Send back to backend as ISO 8601 with 'Z' suffix
 */

import { z } from 'zod'

/**
 * Zod schema for UTC datetime strings.
 *
 * Validates ISO 8601 format with timezone offset.
 * Backend always sends 'Z' suffix (UTC), but this accepts any valid offset.
 */
export const utcDatetimeSchema = z.string().datetime({ offset: true })

/**
 * Parse ISO 8601 UTC string to JavaScript Date.
 *
 * @param isoString - ISO 8601 string (e.g., '2025-01-15T10:30:00Z')
 * @returns JavaScript Date object (UTC internally)
 */
export function parseUTCDatetime(isoString: string): Date {
  return new Date(isoString)
}

/**
 * Format Date as ISO 8601 with 'Z' suffix for backend.
 *
 * @param date - JavaScript Date object
 * @returns ISO 8601 string with 'Z' suffix (e.g., '2025-01-15T10:30:00.123Z')
 */
export function formatUTCDatetime(date: Date): string {
  return date.toISOString()
}

/**
 * Format Date for display in user's local timezone.
 *
 * @param date - JavaScript Date object
 * @param options - Intl.DateTimeFormatOptions (optional)
 * @returns Formatted string in user's local timezone
 *
 * @example
 * ```typescript
 * const date = parseUTCDatetime('2025-01-15T10:30:00Z')
 * formatLocalDatetime(date) // '1/15/2025, 10:30:00 AM' (varies by locale)
 * formatLocalDatetime(date, {
 *   dateStyle: 'medium',
 *   timeStyle: 'short'
 * }) // 'Jan 15, 2025, 10:30 AM'
 * ```
 */
export function formatLocalDatetime(
  date: Date,
  options?: Intl.DateTimeFormatOptions,
): string {
  const defaultOptions: Intl.DateTimeFormatOptions = {
    dateStyle: 'medium',
    timeStyle: 'short',
    ...options,
  }
  return new Intl.DateTimeFormat(undefined, defaultOptions).format(date)
}

/**
 * Get relative time string (e.g., '2 hours ago', 'in 5 minutes').
 *
 * @param date - JavaScript Date object
 * @returns Relative time string in user's locale
 */
export function formatRelativeTime(date: Date): string {
  const now = new Date()
  const diffMs = now.getTime() - date.getTime()
  const diffSec = Math.floor(diffMs / 1000)
  const diffMin = Math.floor(diffSec / 60)
  const diffHour = Math.floor(diffMin / 60)
  const diffDay = Math.floor(diffHour / 24)

  const rtf = new Intl.RelativeTimeFormat(undefined, { numeric: 'auto' })

  if (Math.abs(diffDay) >= 1) return rtf.format(-diffDay, 'day')
  if (Math.abs(diffHour) >= 1) return rtf.format(-diffHour, 'hour')
  if (Math.abs(diffMin) >= 1) return rtf.format(-diffMin, 'minute')
  return rtf.format(-diffSec, 'second')
}

/**
 * Validate that a string is a valid UTC datetime.
 *
 * @param value - String to validate
 * @returns true if valid, false otherwise
 */
export function isValidUTCDatetime(value: string): boolean {
  return utcDatetimeSchema.safeParse(value).success
}

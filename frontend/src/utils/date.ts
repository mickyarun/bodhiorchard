// Copyright 2025-2026 Arun Rajkumar
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

/**
 * Shared date formatting utilities.
 *
 * Centralizes the date-to-human-readable conversion so every component
 * uses the same format and avoids duplicating the same function.
 */

/**
 * Format an ISO-8601 date string into a human-readable local datetime.
 * Returns the raw string unchanged if parsing fails, or empty string for null.
 */
export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return ''
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  return d.toLocaleString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

/**
 * Format an ISO-8601 date string into a date-only label (no time).
 * Returns empty string for null/undefined; falls back to the raw
 * string if parsing fails.
 */
export function formatDate(iso: string | null | undefined): string {
  if (!iso) return ''
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  return d.toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  })
}

/** Month and day only, e.g. "Oct 27". Empty string for null; the raw string if unparseable. */
export function formatShortDate(iso: string | null | undefined): string {
  if (!iso) return ''
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
}

const MINUTE_MS = 60_000
const HOUR_MS = 60 * MINUTE_MS

/**
 * How long ago a timestamp was, for list rows: "just now", "5 minutes ago",
 * "2 hours ago", "yesterday", "3 days ago", then the month and day.
 * Days count calendar days in local time. Empty string for null.
 */
export function relativeTime(iso: string | null | undefined, now: Date): string {
  if (!iso) return ''
  const then = new Date(iso)
  if (Number.isNaN(then.getTime())) return iso
  const diff = now.getTime() - then.getTime()
  if (diff < MINUTE_MS) return 'just now'
  if (diff < HOUR_MS) {
    const mins = Math.floor(diff / MINUTE_MS)
    return mins === 1 ? '1 minute ago' : `${mins} minutes ago`
  }
  const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate())
  if (then >= startOfToday) {
    const hours = Math.floor(diff / HOUR_MS)
    return hours === 1 ? '1 hour ago' : `${hours} hours ago`
  }
  const startOfThen = new Date(then.getFullYear(), then.getMonth(), then.getDate())
  const days = Math.round((startOfToday.getTime() - startOfThen.getTime()) / (24 * HOUR_MS))
  if (days === 1) return 'yesterday'
  if (days < 7) return `${days} days ago`
  return formatShortDate(iso)
}

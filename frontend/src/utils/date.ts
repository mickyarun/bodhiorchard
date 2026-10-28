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
  return monthDay(d)
}

function monthDay(d: Date): string {
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
}

const MINUTE_MS = 60_000
const HOUR_MS = 60 * MINUTE_MS
const DAY_MS = 24 * HOUR_MS

export interface RelativeTimeOptions {
  /** `'short'` writes "5m ago", "2h ago", "3d ago" from elapsed time;
   *  the default spells it out and counts calendar days. */
  style?: 'long' | 'short'
  /** Past a week: `'date'` (default) shows the month and day; `'span'`
   *  keeps counting ("3 weeks ago", "4 months ago", or "45d ago" when short). */
  older?: 'date' | 'span'
  /** `'day'` ignores the time of day and starts at "today" (long style only). */
  granularity?: 'minute' | 'day'
}

/** "5m ago", "2h ago", "45d ago" for compact activity rows; never falls back to a date. */
export const SHORT_AGO: RelativeTimeOptions = { style: 'short', older: 'span' }

/**
 * How long ago a timestamp was, for list rows: "just now", "5 minutes ago",
 * "2 hours ago", "yesterday", "3 days ago", then the month and day.
 * Days count calendar days in local time. Empty string for null.
 * Pass a `Date` for date-only values so they are read as local midnight.
 */
export function relativeTime(
  when: string | Date | null | undefined,
  now: Date,
  options: RelativeTimeOptions = {},
): string {
  if (!when) return ''
  const then = when instanceof Date ? when : new Date(when)
  if (Number.isNaN(then.getTime())) return typeof when === 'string' ? when : ''
  const older = options.older ?? 'date'
  return options.style === 'short'
    ? shortAgo(then, now, older)
    : longAgo(then, now, older, options.granularity ?? 'minute')
}

function shortAgo(then: Date, now: Date, older: 'date' | 'span'): string {
  const mins = Math.floor((now.getTime() - then.getTime()) / MINUTE_MS)
  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins}m ago`
  const hours = Math.floor(mins / 60)
  if (hours < 24) return `${hours}h ago`
  const days = Math.floor(hours / 24)
  if (older === 'date' && days >= 7) return monthDay(then)
  return `${days}d ago`
}

function longAgo(
  then: Date,
  now: Date,
  older: 'date' | 'span',
  granularity: 'minute' | 'day',
): string {
  const startOfToday = startOfDay(now)
  if (granularity === 'minute') {
    const diff = now.getTime() - then.getTime()
    if (diff < MINUTE_MS) return 'just now'
    if (diff < HOUR_MS) {
      const mins = Math.floor(diff / MINUTE_MS)
      return mins === 1 ? '1 minute ago' : `${mins} minutes ago`
    }
    if (then >= startOfToday) {
      const hours = Math.floor(diff / HOUR_MS)
      return hours === 1 ? '1 hour ago' : `${hours} hours ago`
    }
  }
  const days = Math.round((startOfToday.getTime() - startOfDay(then).getTime()) / DAY_MS)
  if (days <= 0) return 'today'
  if (days === 1) return 'yesterday'
  if (older === 'span') return daySpan(days)
  if (days < 7) return `${days} days ago`
  return monthDay(then)
}

/** "5 days ago" up to a fortnight, then weeks, months and years. */
function daySpan(days: number): string {
  if (days < 14) return `${days} days ago`
  if (days < 63) return `${Math.floor(days / 7)} weeks ago`
  const months = Math.floor(days / 30.44)
  return months < 24 ? `${months} months ago` : `${Math.floor(months / 12)} years ago`
}

function startOfDay(d: Date): Date {
  return new Date(d.getFullYear(), d.getMonth(), d.getDate())
}

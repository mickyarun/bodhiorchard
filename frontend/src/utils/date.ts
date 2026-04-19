// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Arun Rajkumar

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

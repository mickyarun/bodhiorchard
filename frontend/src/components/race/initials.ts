// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Arun Rajkumar

/**
 * `initials` — compact avatar-text helper shared across race surfaces
 * (lobby slots, results list, setup dialog). Three different components
 * had drifted on whether a trailing ellipsis counts, how to handle
 * single-word names, etc. — consolidating here keeps avatar labels
 * consistent everywhere a name is reduced to a circle chip.
 *
 *   initials('Alice Kim')      → 'AK'
 *   initials('Bob')            → 'B'
 *   initials('38ca3…')         → '3'   (ellipsis is stripped)
 *   initials('')               → '?'
 */
export function initials(name: string): string {
  if (!name) return '?'
  // UUID-ish fallback values sometimes arrive with a trailing ellipsis
  // ("38ca3fde…"). The ellipsis isn't a real character of the name so
  // dropping it prevents weirdness like "3…" → "3".
  const cleaned = name.replace(/…$/, '').trim()
  if (!cleaned) return '?'
  const parts = cleaned.split(/\s+/)
  const first = parts[0][0] ?? ''
  const last = parts.length > 1 ? parts[parts.length - 1][0] ?? '' : ''
  return (first + last).toUpperCase() || '?'
}

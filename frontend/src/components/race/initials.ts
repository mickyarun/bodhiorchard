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

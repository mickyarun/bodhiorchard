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

/** IANA timezone names for pickers. */

// Hand-picked short list for browsers without `Intl.supportedValuesOf`
// (Chrome < 99, Firefox < 93, Safari < 15.4).
export const FALLBACK_TIMEZONES: readonly string[] = [
  'UTC',
  'America/New_York', 'America/Chicago', 'America/Denver', 'America/Los_Angeles',
  'Europe/London', 'Europe/Paris', 'Europe/Berlin', 'Europe/Madrid',
  'Asia/Tokyo', 'Asia/Shanghai', 'Asia/Singapore', 'Asia/Kolkata', 'Asia/Dubai',
  'Australia/Sydney', 'Pacific/Auckland',
]

type SupportedValuesOf = (key: string) => string[]

/** Every timezone the browser knows, or the short fallback list. */
export function supportedTimezones(): string[] {
  try {
    const supportedValuesOf = (Intl as unknown as { supportedValuesOf?: SupportedValuesOf })
      .supportedValuesOf
    if (typeof supportedValuesOf === 'function') return supportedValuesOf('timeZone')
  } catch {
    // Older engines throw on unknown keys; use the fallback below.
  }
  return [...FALLBACK_TIMEZONES]
}

/** Picker options: the known zones plus UTC and the current value, sorted
 *  and without duplicates, so a saved value always shows as selected. */
export function timezoneOptions(
  current: string | null | undefined,
  known: readonly string[] = supportedTimezones(),
): string[] {
  const all = new Set(known)
  all.add('UTC')
  if (current) all.add(current)
  return [...all].sort((a, b) => a.localeCompare(b))
}

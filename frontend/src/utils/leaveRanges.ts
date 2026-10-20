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
 * Date-range presets for leave reports and the approvals filter.
 *
 * Pure: `today` is passed in so tests pin it. Dates are local
 * 'YYYY-MM-DD' strings, the same as everywhere else in leave.
 */
import { toIsoDate } from '@/utils/leaveDates'

export interface DateRange {
  start: string
  end: string
}

export type RangePreset =
  | 'this_week'
  | 'this_month'
  | 'last_month'
  | 'next_30_days'
  | 'this_quarter'
  | 'this_year'
  | 'custom'

export const RANGE_LABELS: Record<RangePreset, string> = {
  this_week: 'This week',
  this_month: 'This month',
  last_month: 'Last month',
  next_30_days: 'Next 30 days',
  this_quarter: 'This quarter',
  this_year: 'This year',
  custom: 'Custom',
}

function at(year: number, month: number, day: number): string {
  return toIsoDate(new Date(year, month, day))
}

/** The range a preset means on `today`; `custom` keeps `current`. */
export function presetRange(preset: RangePreset, today: Date, current?: DateRange): DateRange {
  const y = today.getFullYear()
  const m = today.getMonth()
  const d = today.getDate()
  switch (preset) {
    case 'this_week': {
      const monday = d - ((today.getDay() + 6) % 7)
      return { start: at(y, m, monday), end: at(y, m, monday + 6) }
    }
    case 'this_month':
      return { start: at(y, m, 1), end: at(y, m + 1, 0) }
    case 'last_month':
      return { start: at(y, m - 1, 1), end: at(y, m, 0) }
    case 'next_30_days':
      return { start: at(y, m, d), end: at(y, m, d + 29) }
    case 'this_quarter': {
      const first = m - (m % 3)
      return { start: at(y, first, 1), end: at(y, first + 3, 0) }
    }
    case 'this_year':
      return { start: at(y, 0, 1), end: at(y, 11, 31) }
    case 'custom':
      return current ?? { start: at(y, m, 1), end: at(y, m + 1, 0) }
  }
}

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

/** Select options shared by the leave filter bars. */
import type { LeaveKind, LeaveStatus } from '@/types/leave'
import { KIND_LABELS, STATUS_META } from '@/utils/leave'

export interface SelectOption<T> {
  title: string
  value: T
}

export const KIND_OPTIONS: SelectOption<LeaveKind>[] = (Object.keys(KIND_LABELS) as LeaveKind[]).map(
  value => ({ value, title: KIND_LABELS[value] }),
)

export const STATUS_OPTIONS: SelectOption<LeaveStatus>[] = (
  Object.keys(STATUS_META) as LeaveStatus[]
).map(value => ({ value, title: STATUS_META[value].label }))

/** Past leave years offered next to the current one. */
const PAST_YEARS = 2

/**
 * "Current leave year" (null: each person's own) plus nearby leave-year
 * labels. A label is the year a leave year starts in, so it comes from the
 * API, not the calendar: an April-start year is still "2025" in March 2026.
 * Several labels mean policies whose years start in different months.
 */
export function leaveYearOptions(current: readonly number[]): SelectOption<number | null>[] {
  const options: SelectOption<number | null>[] = [{ title: 'Current leave year', value: null }]
  if (!current.length) return options
  const newest = Math.max(...current) + 1
  const oldest = Math.min(...current) - PAST_YEARS
  for (let label = newest; label >= oldest; label--) {
    options.push({ title: String(label), value: label })
  }
  return options
}

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

/** Labels and pure helpers for employee records. */
import type {
  BloodGroup,
  EmployeeStatus,
  EmploymentType,
  Gender,
  ManagerInput,
} from '@/types/employee'

export const EMPLOYMENT_TYPE_LABELS: Record<EmploymentType, string> = {
  full_time: 'Full time',
  part_time: 'Part time',
  contract: 'Contract',
  intern: 'Intern',
}

export const STATUS_LABELS: Record<EmployeeStatus, string> = {
  active: 'Active',
  on_notice: 'On notice',
  exited: 'Exited',
}

export const GENDER_LABELS: Record<Gender, string> = {
  female: 'Female',
  male: 'Male',
  non_binary: 'Non-binary',
  prefer_not_to_say: 'Prefer not to say',
}

export const BLOOD_GROUP_LABELS: Record<BloodGroup, string> = {
  a_positive: 'A+',
  a_negative: 'A−',
  b_positive: 'B+',
  b_negative: 'B−',
  ab_positive: 'AB+',
  ab_negative: 'AB−',
  o_positive: 'O+',
  o_negative: 'O−',
}

/** `{ title, value }` items for a v-select from a label map. */
export function selectItems<T extends string>(labels: Record<T, string>): { title: string; value: T }[] {
  return (Object.keys(labels) as T[]).map(value => ({ title: labels[value], value }))
}

/**
 * Format an ISO date-only string ("2026-10-20") as "20 Oct 2026".
 *
 * Parsed as a local date: `new Date('2026-10-20')` is UTC midnight and
 * renders as the 19th west of Greenwich.
 */
export function formatDateOnly(iso: string | null): string {
  if (!iso) return '—'
  const [year, month, day] = iso.split('-').map(Number)
  if (!year || !month || !day) return iso
  return new Date(year, month - 1, day).toLocaleDateString('en-GB', {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
  })
}

/**
 * Apply a manager-list edit: one entry per person, exactly one primary
 * when the list isn't empty (the first, unless another is marked).
 */
export function normalizeManagers(managers: ManagerInput[]): ManagerInput[] {
  const unique = managers.filter(
    (m, index) => managers.findIndex(other => other.user_id === m.user_id) === index,
  )
  if (unique.length === 0) return []
  const primaryIndex = Math.max(
    0,
    unique.findIndex(m => m.is_primary),
  )
  return unique.map((m, index) => ({ user_id: m.user_id, is_primary: index === primaryIndex }))
}

/** Make `userId` the only primary manager. */
export function setPrimary(managers: ManagerInput[], userId: string): ManagerInput[] {
  return managers.map(m => ({ user_id: m.user_id, is_primary: m.user_id === userId }))
}

/** Empty form inputs become \`null\`, which the API treats as "not set". */
export function blankToNull<T extends object>(values: T): T {
  const out = { ...values } as Record<string, unknown>
  for (const key of Object.keys(out)) {
    if (out[key] === '') out[key] = null
  }
  return out as T
}

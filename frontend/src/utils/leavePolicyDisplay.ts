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

/** Pure text helpers for the leave settings screens. */
import type { Gender } from '@/types/employee'
import type { HolidaySource } from '@/types/leave'
import type { HolidayAdminRead, LeaveTypeRead, PolicyRead, PolicyWrite } from '@/types/leavePolicy'
import { pluralDays, SWATCH_KEYS, toNumberOrNull } from '@/utils/leave'
import { MONTH_NAMES, WEEKDAY_SHORT } from '@/utils/leaveDates'
import { GENDER_LABELS } from '@/utils/employee'

/** Shared props for every settings form field. */
export const FIELD_PROPS = { variant: 'outlined', density: 'comfortable', hideDetails: 'auto' } as const

/** Readable names for the leave colour swatches, in swatch order. */
const SWATCH_NAMES = ['Green', 'Blue', 'Amber', 'Red', 'Gold', 'Teal', 'Grey']

export const SWATCH_OPTIONS = SWATCH_KEYS.map((key, index) => ({
  key,
  name: SWATCH_NAMES[index] ?? `Colour ${index + 1}`,
}))

export const HOLIDAY_SOURCE_LABELS: Record<HolidaySource, string> = {
  imported: 'Imported',
  manual: 'Added',
}

export const WORK_WEEK_PRESETS = [
  { label: 'Mon–Fri', days: [0, 1, 2, 3, 4] },
  { label: 'Mon–Sat', days: [0, 1, 2, 3, 4, 5] },
] as const

export type PolicySection = 'types' | 'holidays' | 'rules' | 'people' | 'history'

/** A policy's sections, in nav order (`?section=`). */
export const POLICY_SECTIONS: { value: PolicySection; title: string; icon: string }[] = [
  { value: 'types', title: 'Leave types', icon: 'mdi-shape-outline' },
  { value: 'holidays', title: 'Holidays', icon: 'mdi-calendar-star' },
  { value: 'rules', title: 'Rules', icon: 'mdi-tune-variant' },
  { value: 'people', title: 'People', icon: 'mdi-account-multiple-outline' },
  { value: 'history', title: 'History', icon: 'mdi-history' },
]

/** The section named in the URL, or the first one. */
export function parseSection(value: unknown): PolicySection {
  return POLICY_SECTIONS.find(s => s.value === value)?.value ?? 'types'
}

/** "1 person", "12 people". */
export function peopleCount(count: number): string {
  return `${count} ${count === 1 ? 'person' : 'people'}`
}

/** "Mon–Fri" for a run of days, "Mon, Wed, Fri" otherwise, "Every day" for all 7. */
export function workWeekLabel(days: readonly number[]): string {
  const sorted = [...new Set(days)].sort((a, b) => a - b)
  if (!sorted.length) return 'No working days'
  if (sorted.length === 7) return 'Every day'
  const consecutive = sorted.every((day, index) => index === 0 || day === sorted[index - 1] + 1)
  if (consecutive && sorted.length > 2) {
    return `${WEEKDAY_SHORT[sorted[0]]}–${WEEKDAY_SHORT[sorted[sorted.length - 1]]}`
  }
  return sorted.map(day => WEEKDAY_SHORT[day]).join(', ')
}

/** "12 people · Mon–Fri · Year starts April". */
export function policyStatLine(policy: PolicyRead): string {
  return [
    peopleCount(policy.employee_count),
    workWeekLabel(policy.working_days),
    `Year starts ${MONTH_NAMES[policy.year_start_month - 1]}`,
  ].join(' · ')
}

/** One line on how work-from-home requests are approved. */
export function wfhRuleCaption(
  policy: Pick<PolicyWrite, 'wfh_approval' | 'wfh_monthly_auto_days'>,
): string {
  switch (policy.wfh_approval) {
    case 'auto':
      return 'Work from home is approved automatically'
    case 'auto_within_allowance':
      return `Work from home is approved automatically up to ${pluralDays(policy.wfh_monthly_auto_days)} a month`
    default:
      return 'Work from home always needs approval'
  }
}

/** Why a policy can't be deleted yet, or null when it can. */
export function deleteBlocker(policy: PolicyRead): string | null {
  if (policy.is_default) return 'Make another policy the default first'
  if (policy.employee_count > 0) return 'Move its people off first'
  if (policy.has_requests) return 'Leave was requested on it, so it stays'
  return null
}

/** "12 days", "18 days, earned monthly" or "Unlimited". */
export function allowanceLabel(type: Pick<LeaveTypeRead, 'annual_quota_days' | 'accrual'>): string {
  const quota = toNumberOrNull(type.annual_quota_days)
  if (quota === null) return 'Unlimited'
  return type.accrual === 'monthly' ? `${pluralDays(quota)}, earned monthly` : pluralDays(quota)
}

/** "Female", "Female, Non-binary": who a gender-limited type is for. */
export function gendersLabel(genders: readonly Gender[]): string {
  return genders.map(g => GENDER_LABELS[g]).join(', ')
}

/** Short tags for a type's special rules, e.g. ["Women only", "Auto-approved", "1 day a month"]. */
export function typeRuleTags(
  type: Pick<LeaveTypeRead, 'eligible_genders' | 'auto_approve' | 'monthly_limit_days'>,
): string[] {
  const tags: string[] = []
  if (type.eligible_genders) tags.push(`${gendersLabel(type.eligible_genders)} only`)
  if (type.auto_approve) tags.push('Auto-approved')
  const perMonth = toNumberOrNull(type.monthly_limit_days)
  if (perMonth !== null) tags.push(`${pluralDays(perMonth)} a month`)
  return tags
}

/** Active types first as given, switched-off ones apart. */
export function splitLeaveTypes(types: readonly LeaveTypeRead[]): {
  active: LeaveTypeRead[]
  inactive: LeaveTypeRead[]
} {
  return {
    active: types.filter(t => t.is_active),
    inactive: types.filter(t => !t.is_active),
  }
}

/** "14 holidays, 3 optional", "1 holiday", or "No holidays yet". */
export function holidaySummary(holidays: readonly Pick<HolidayAdminRead, 'kind'>[]): string {
  if (!holidays.length) return 'No holidays yet'
  const total = `${holidays.length} ${holidays.length === 1 ? 'holiday' : 'holidays'}`
  const optional = holidays.filter(h => h.kind === 'optional').length
  return optional ? `${total}, ${optional} optional` : total
}

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

/** Plain-language lines for a policy's configuration history. */
import type { Gender } from '@/types/employee'
import type { ConfigEventRead } from '@/types/leavePolicy'
import { MONTH_NAMES, WEEKDAY_SHORT } from '@/utils/leaveDates'
import { gendersLabel } from '@/utils/leavePolicyDisplay'

const NUMERIC = /^-?\d+(\.\d+)?$/

const FIELD_LABELS: Record<string, string> = {
  name: 'Name',
  country_code: 'Country',
  subdivision_code: 'Region',
  timezone: 'Timezone',
  working_days: 'Working days',
  year_start_month: 'Leave year starts',
  wfh_approval: 'WFH approval',
  wfh_monthly_auto_days: 'WFH days approved automatically',
  backdate_limit_days: 'Backdating limit (days)',
  optional_holiday_quota: 'Optional holidays',
  proration_method: 'Prorate new joiners',
  proration_cutoff_day: 'Joining-month cutoff day',
  allocation_rounding: 'Rounding',
  code: 'Code',
  annual_quota_days: 'Yearly quota',
  accrual: 'Given',
  is_paid: 'Paid',
  is_encashable: 'Encashable at exit',
  counts_toward_warning: 'Counts toward high-leave warning',
  eligible_genders: 'Who can use it',
  auto_approve: 'Approved automatically',
  monthly_limit_days: 'Most days in a month',
  leave_notice_days: 'High-leave heads-up (days)',
  leave_warning_days: 'High-leave warning (days)',
  color_key: 'Colour',
  is_active: 'Active',
  is_default: 'Default policy',
}

function formatValue(field: string, value: unknown): string {
  if (value === null || value === undefined) {
    return field === 'annual_quota_days' || field === 'monthly_limit_days'
      ? 'no limit'
      : field === 'eligible_genders'
        ? 'everyone'
        : '—'
  }
  if (field === 'working_days' && Array.isArray(value)) {
    return value.map(day => WEEKDAY_SHORT[Number(day)] ?? String(day)).join(', ')
  }
  if (field === 'year_start_month') return MONTH_NAMES[Number(value) - 1] ?? String(value)
  if (field === 'accrual') return value === 'upfront' ? 'all at once' : String(value)
  if (field === 'eligible_genders' && Array.isArray(value)) return `${gendersLabel(value as Gender[])} only`
  if (typeof value === 'boolean') return value ? 'yes' : 'no'
  // Decimals arrive as strings ("7.0"); show them as numbers ("7").
  if (typeof value === 'string' && NUMERIC.test(value)) return String(Number(value))
  if (Array.isArray(value)) return value.join(', ')
  return String(value).replace(/_/g, ' ')
}

/** "Yearly quota: 12 → 15" for each changed field (the type code is shown separately). */
export function changeLines(changes: Record<string, unknown>): string[] {
  return Object.entries(changes)
    // Only known fields: assignments carry a list of ids that isn't a change.
    .filter(([field, pair]) => field in FIELD_LABELS && Array.isArray(pair) && pair.length === 2)
    .map(([field, pair]) => {
      const [before, after] = pair as [unknown, unknown]
      const label = FIELD_LABELS[field] ?? field
      return before === null || before === undefined
        ? `${label}: ${formatValue(field, after)}`
        : `${label}: ${formatValue(field, before)} → ${formatValue(field, after)}`
    })
}

/** One-line summary of what happened. */
export function eventTitle(event: ConfigEventRead): string {
  const type = typeof event.changes.type === 'string' ? event.changes.type : ''
  switch (event.action) {
    case 'policy_created':
      return 'Created the policy'
    case 'policy_updated':
      return 'Changed the policy'
    case 'policy_made_default':
      return 'Made this the default policy'
    case 'policy_deleted':
      return 'Deleted the policy'
    case 'type_created':
      return `Added leave type ${type}`
    case 'type_updated':
      return `Changed leave type ${type}`
    case 'employees_assigned': {
      const count = Number(event.changes.assigned ?? 0)
      return `Moved ${count} ${count === 1 ? 'person' : 'people'} onto this policy`
    }
  }
}

/** "Was 12 days, now 6.5: booked −5.5 days." or "Already matches the current rules." */
export function recalculationSummary(result: {
  frozen: string | number
  recalculated: string | number
  correction: string | number
}): string {
  const correction = Number(result.correction)
  if (!correction) return 'Already matches the current rules; nothing changed.'
  const sign = correction > 0 ? '+' : '−'
  return `Was ${Number(result.frozen)} days, now ${Number(result.recalculated)}: booked ${sign}${Math.abs(correction)} days.`
}

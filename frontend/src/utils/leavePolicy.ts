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

/** Pure helpers for the leave policy settings screens. */
import type { HolidayKind } from '@/types/leave'
import type {
  AllocationRounding,
  HolidayCountry,
  PolicyRead,
  PolicyWrite,
  ProrationMethod,
} from '@/types/leavePolicy'
import { MONTH_NAMES } from '@/utils/leaveDates'

/** A new policy's starting values (match the API's own defaults). */
export function newPolicy(): PolicyWrite {
  return {
    name: '',
    country_code: null,
    subdivision_code: null,
    timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC',
    working_days: [0, 1, 2, 3, 4],
    year_start_month: 1,
    wfh_approval: 'required',
    wfh_monthly_auto_days: 0,
    backdate_limit_days: 7,
    optional_holiday_quota: 0,
    proration_method: 'daily',
    proration_cutoff_day: 15,
    allocation_rounding: 'nearest_half',
  }
}

/** The writable part of a policy, for a PUT. */
export function policyToWrite(policy: PolicyRead): PolicyWrite {
  return {
    name: policy.name,
    country_code: policy.country_code,
    subdivision_code: policy.subdivision_code,
    timezone: policy.timezone,
    working_days: [...policy.working_days],
    year_start_month: policy.year_start_month,
    wfh_approval: policy.wfh_approval,
    wfh_monthly_auto_days: policy.wfh_monthly_auto_days,
    backdate_limit_days: policy.backdate_limit_days,
    optional_holiday_quota: policy.optional_holiday_quota,
    proration_method: policy.proration_method,
    proration_cutoff_day: policy.proration_cutoff_day,
    allocation_rounding: policy.allocation_rounding,
  }
}

export const PRORATION_LABELS: Record<ProrationMethod, string> = {
  daily: 'By days left in the leave year',
  monthly: 'By whole months left in the leave year',
  none: "Don't prorate: full quota",
}

export const ROUNDING_LABELS: Record<AllocationRounding, string> = {
  nearest_half: 'Nearest half day',
  up_half: 'Up to the next half day',
  down_half: 'Down to the previous half day',
  nearest_whole: 'Nearest whole day',
  up_whole: 'Up to the next whole day',
  down_whole: 'Down to the previous whole day',
  none: "Don't round (one decimal place)",
}

/** "India – Tamil Nadu", "India", or "" when no country is set. */
export function regionLabel(
  countries: HolidayCountry[],
  countryCode: string | null,
  subdivisionCode: string | null,
): string {
  if (!countryCode) return ''
  const country = countries.find(c => c.code === countryCode)
  const name = country?.name ?? countryCode
  if (!subdivisionCode) return name
  const sub = country?.subdivisions.find(s => s.code === subdivisionCode)
  return `${name} – ${sub?.name ?? subdivisionCode}`
}

export const MONTH_ITEMS = MONTH_NAMES.map((title, index) => ({ title, value: index + 1 }))

export const HOLIDAY_KIND_OPTIONS: { label: string; value: HolidayKind }[] = [
  { label: 'Mandatory', value: 'mandatory' },
  { label: 'Optional', value: 'optional' },
]

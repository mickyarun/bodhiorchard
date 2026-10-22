/**
 * Copyright 2025-2026 Arun Rajkumar
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

/** Starting points for the leave type dialog: blank, an existing type, or period leave. */
import type { Decimalish } from '@/types/leave'
import type { LeaveTypeRead, LeaveTypeWrite } from '@/types/leavePolicy'
import { SWATCH_KEYS } from '@/utils/leave'

export function blankType(): LeaveTypeWrite {
  return {
    name: '',
    code: '',
    annual_quota_days: null,
    accrual: 'upfront',
    is_paid: true,
    is_encashable: false,
    counts_toward_warning: true,
    eligible_genders: null,
    auto_approve: false,
    monthly_limit_days: null,
    stops_at_balance: false,
    color_key: SWATCH_KEYS[0],
    is_active: true,
  }
}

export function draftFromType(type: LeaveTypeRead): LeaveTypeWrite {
  const { id: _id, policy_id: _policy, template_id: _template, own_quota: _own, ...write } = type
  return write
}

/** Period leave: one paid day a month for women, taken on notice rather than
 *  permission, so it approves itself and an unused day lapses with the month. */
export function periodLeave(): LeaveTypeWrite {
  return {
    ...blankType(),
    name: 'Period leave',
    code: 'PERIOD',
    annual_quota_days: 12,
    eligible_genders: ['female'],
    auto_approve: true,
    monthly_limit_days: 1,
    // Separate from other leave: it shouldn't push anyone toward the warning.
    counts_toward_warning: false,
    color_key: SWATCH_KEYS[5] ?? SWATCH_KEYS[0],
  }
}

/** No limit, or half-day steps from 0.5 to 31 (what the server accepts). */
export function validMonthlyLimit(value: Decimalish | null): boolean {
  if (value === null) return true
  if (value === '') return false
  const days = Number(value)
  return days >= 0.5 && days <= 31 && Number.isInteger(days * 2)
}

/** True once a policy has period leave (on or off), so the shortcut steps aside. */
export function hasPeriodLeave(types: LeaveTypeRead[]): boolean {
  const code = periodLeave().code
  return types.some(t => t.code === code)
}

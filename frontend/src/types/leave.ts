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
 * Leave, WFH and optional-holiday types, mirroring
 * backend/app/schemas/leave.py (configuration types are in leavePolicy.ts).
 *
 * Decimal fields arrive as JSON strings or numbers (`Decimalish`); read
 * them through `toNumber()` in utils/leave.ts. Dates are 'YYYY-MM-DD'.
 */

import type { WorkArrangement } from '@/types/employee'

export type Decimalish = number | string

export type LeaveKind = 'leave' | 'wfh' | 'optional_holiday'
export type HalfDay = 'none' | 'first_half' | 'second_half'
export type LeaveStatus = 'pending' | 'approved' | 'rejected' | 'cancelled'
export type ApprovalMode = 'manual' | 'auto_policy'
export type WfhApproval = 'required' | 'auto' | 'auto_within_allowance'
export type HolidayKind = 'mandatory' | 'optional'
export type HolidaySource = 'manual' | 'imported'
export type ApprovalRoute = 'manager' | 'hr_queue' | 'hr_override'
export type RequestScope = 'upcoming' | 'past' | 'all'
export type SwatchKey = `swatch-${1 | 2 | 3 | 4 | 5 | 6 | 7}`

export interface LeaveTypeBrief {
  id: string
  name: string
  code: string
  color_key: string
}

export interface HolidayRead {
  id: string
  date: string
  name: string
  kind: HolidayKind
}

export interface LeaveYear {
  label: number
  start: string
  end: string
}

export interface PolicyBrief {
  id: string
  name: string
  timezone: string
  working_days: number[]
  year_start_month: number
  wfh_approval: WfhApproval
  wfh_monthly_auto_days: number
  backdate_limit_days: number
  optional_holiday_quota: number
}

/** `allocated` / `available` are null when the type has no limit. */
export interface Balance {
  leave_type: LeaveTypeBrief
  is_paid: boolean
  allocated: Decimalish | null
  adjustments: Decimalish
  used: Decimalish
  pending: Decimalish
  available: Decimalish | null
}

export interface OptionalHolidayBalance {
  quota: number
  used: number
  pending: number
  remaining: number
  holidays: HolidayRead[]
}

export interface PersonRef {
  user_id: string
  name: string
}

export interface LeaveSummary {
  policy: PolicyBrief
  leave_year: LeaveYear
  balances: Balance[]
  optional_holidays: OptionalHolidayBalance
  wfh_auto_days_left_this_month: number | null
  /** Loss-of-pay days this leave year (approved or pending). */
  lop_days: Decimalish
  approvers: PersonRef[]
  routes_to_hr: boolean
  /** Remote people have no WFH option. */
  work_arrangement: WorkArrangement
}

export interface LeaveRequestCreate {
  kind: LeaveKind
  leave_type_id: string | null
  holiday_id: string | null
  start_date: string
  end_date: string
  half_day: HalfDay
  reason: string | null
}

export interface ExcludedDate {
  date: string
  reason: string
}

export interface LeaveProblem {
  code: string
  message: string
}

export interface LeavePreview {
  days: Decimalish
  /** Days past the balance: taken as loss of pay. */
  lop_days: Decimalish
  excluded: ExcludedDate[]
  balance_before: Decimalish | null
  balance_after: Decimalish | null
  auto_approved: boolean
  approvers: PersonRef[]
  routes_to_hr: boolean
  problems: LeaveProblem[]
}

export interface LeaveRequestRead {
  id: string
  user: PersonRef
  kind: LeaveKind
  leave_type: LeaveTypeBrief | null
  holiday_name: string | null
  start_date: string
  end_date: string
  half_day: HalfDay
  days: Decimalish
  lop_days: Decimalish
  reason: string | null
  status: LeaveStatus
  approval_mode: ApprovalMode
  decided_by: PersonRef | null
  decided_at: string | null
  decision_note: string | null
  created_at: string
  can_cancel: boolean
}

export interface AlsoOut {
  name: string
  kind: LeaveKind
  start_date: string
  end_date: string
}

export interface ApprovalItem {
  request: LeaveRequestRead
  route: ApprovalRoute
  designation: string | null
  department: string | null
  balance_after: Decimalish | null
  also_out: AlsoOut[]
}

export interface ApprovalCount {
  pending: number
  is_approver: boolean
}

/** `leave_type` / `reason` are only set for HR, the requester and managers. */
export interface CalendarEntry {
  request_id: string
  user: PersonRef
  kind: LeaveKind
  start_date: string
  end_date: string
  half_day: HalfDay
  status: LeaveStatus
  is_own: boolean
  leave_type: LeaveTypeBrief | null
  reason: string | null
  /** The requester's own working days (0 = Mon). */
  working_days: number[]
}

export interface CalendarRead {
  entries: CalendarEntry[]
  holidays: HolidayRead[]
}

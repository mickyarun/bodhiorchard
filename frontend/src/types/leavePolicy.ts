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
 * Leave configuration types (leave:configure), mirroring
 * backend/app/schemas/leave_policy.py. See types/leave.ts for the
 * Decimal and date conventions.
 */
import type {
  Balance,
  Decimalish,
  HolidayKind,
  HolidaySource,
  LeaveYear,
  PersonRef,
  WfhApproval,
} from '@/types/leave'

export type ProrationMethod = 'none' | 'daily' | 'monthly'
export type AllocationRounding =
  | 'none'
  | 'nearest_half'
  | 'up_half'
  | 'down_half'
  | 'nearest_whole'
  | 'up_whole'
  | 'down_whole'

export interface PolicyWrite {
  name: string
  country_code: string | null
  subdivision_code: string | null
  timezone: string
  working_days: number[]
  year_start_month: number
  wfh_approval: WfhApproval
  wfh_monthly_auto_days: number
  backdate_limit_days: number
  optional_holiday_quota: number
  proration_method: ProrationMethod
  /** Monthly proration: joining on or before this day counts the month. */
  proration_cutoff_day: number
  allocation_rounding: AllocationRounding
}

export interface PolicyRead extends PolicyWrite {
  id: string
  is_default: boolean
  employee_count: number
  has_requests: boolean
}

export interface LeaveTypeWrite {
  name: string
  code: string
  annual_quota_days: Decimalish | null
  is_paid: boolean
  color_key: string
  is_active: boolean
}

export interface LeaveTypeRead extends LeaveTypeWrite {
  id: string
  policy_id: string
}

export interface HolidayWrite {
  date: string
  name: string
  kind: HolidayKind
}

export interface HolidayAdminRead extends HolidayWrite {
  id: string
  source: HolidaySource
}

export interface HolidayImportResult {
  added: number
  skipped: number
}

export interface Subdivision {
  code: string
  name: string
}

export interface HolidayCountry {
  code: string
  name: string
  subdivisions: Subdivision[]
}

export interface LedgerEntryRead {
  id: string
  leave_type_id: string
  leave_year: number
  entry_type: string
  days: Decimalish
  note: string | null
  created_by: PersonRef | null
  created_at: string
}

export interface BalanceAdjust {
  leave_type_id: string
  days: number
  note: string
  leave_year: number | null
}

export interface MemberBalances {
  user: PersonRef
  policy_name: string
  leave_year: LeaveYear
  balances: Balance[]
  ledger: LedgerEntryRead[]
}

export interface Recalculate {
  leave_type_id: string
  leave_year: number | null
}

export interface RecalculateResult {
  frozen: Decimalish
  recalculated: Decimalish
  correction: Decimalish
  balances: MemberBalances
}

export type ConfigAction =
  | 'policy_created'
  | 'policy_updated'
  | 'policy_made_default'
  | 'policy_deleted'
  | 'type_created'
  | 'type_updated'
  | 'employees_assigned'

/** One change to a policy or its leave types; `changes` is {field: [old, new]}. */
export interface ConfigEventRead {
  id: string
  action: ConfigAction
  actor: PersonRef
  at: string
  changes: Record<string, unknown>
}

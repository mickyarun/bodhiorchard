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

/** Leave reports (mirrors backend app/schemas/leave_reports.py). Never reasons. */
import type { Decimalish, HalfDay, LeaveKind, LeaveStatus, PersonRef } from '@/types/leave'

export type ReportName = 'summary' | 'register' | 'balances'

export interface NamedRef {
  id: string
  name: string
}

export interface PersonColumns {
  user_id: string
  name: string
  employee_code: string | null
  department: string | null
  office: string | null
  policy: string | null
  manager: string | null
  status: string | null
  is_active: boolean
}

export interface SummaryRow extends PersonColumns {
  leave_by_type: Record<string, Decimalish>
  leave_days: Decimalish
  lop_days: Decimalish
  wfh_days: Decimalish
  optional_holidays: Decimalish
  pending_days: Decimalish
}

export interface SummaryReport {
  start: string
  end: string
  leave_types: NamedRef[]
  rows: SummaryRow[]
}

export interface RegisterRow {
  request_id: string
  user_id: string
  name: string
  employee_code: string | null
  department: string | null
  kind: LeaveKind
  leave_type: string | null
  start_date: string
  end_date: string
  half_day: HalfDay
  days: Decimalish
  lop_days: Decimalish
  status: LeaveStatus
  approval_mode: 'manual' | 'auto_policy'
  requested_at: string
  decided_by: string | null
  decided_at: string | null
}

export interface RegisterReport {
  rows: RegisterRow[]
  truncated: boolean
}

export interface BalanceRow extends PersonColumns {
  leave_year: number
  leave_type: string
  allocated: Decimalish | null
  adjustments: Decimalish
  used: Decimalish
  pending: Decimalish
  available: Decimalish | null
  lop_days: Decimalish
}

export interface BalanceReport {
  rows: BalanceRow[]
}

export interface ReportScope {
  all: boolean
  people: PersonRef[]
  departments: string[]
  offices: NamedRef[]
  policies: NamedRef[]
  leave_types: NamedRef[]
}

/** Every filter the reports take; each report sends only the ones it uses. */
export interface ReportFilters {
  start: string
  end: string
  year: number | null
  user_id: string | null
  department: string | null
  office_id: string | null
  policy_id: string | null
  manager_id: string | null
  kind: LeaveKind | null
  leave_type_id: string | null
  status: LeaveStatus | null
}

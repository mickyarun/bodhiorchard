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

/** Column totals for the leave summary report, keyed like its table
 *  columns: `leave_days`, `type_<index>` per leave type, and the rest. */
import type { SummaryReport } from '@/types/leaveReports'
import { toNumber } from '@/utils/leave'

export const SUMMARY_TOTAL_KEYS = ['leave_days', 'lop_days', 'wfh_days', 'optional_holidays', 'pending_days'] as const

export function summaryTotals(report: SummaryReport | null): Record<string, number> {
  const totals: Record<string, number> = {}
  for (const key of SUMMARY_TOTAL_KEYS) totals[key] = 0
  const types = report?.leave_types ?? []
  types.forEach((_, i) => {
    totals[`type_${i}`] = 0
  })
  for (const row of report?.rows ?? []) {
    for (const key of SUMMARY_TOTAL_KEYS) totals[key] += toNumber(row[key])
    types.forEach((t, i) => {
      totals[`type_${i}`] += toNumber(row.leave_by_type[t.key])
    })
  }
  return totals
}

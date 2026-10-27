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

import { describe, expect, it } from 'vitest'

import type { SummaryReport, SummaryRow } from '@/types/leaveReports'
import { summaryTotals } from '@/utils/leaveReportTotals'

function row(over: Partial<SummaryRow>): SummaryRow {
  return {
    leave_by_type: {},
    left_by_type: {},
    leave_days: '0',
    high_leave: null,
    lop_days: '0',
    wfh_days: '0',
    optional_holidays: 0,
    pending_days: '0',
    ...over,
  } as SummaryRow
}

describe('summaryTotals', () => {
  it('adds every numeric column, one per leave type, decimals included', () => {
    const report = {
      start: '2026-01-01',
      end: '2026-12-31',
      leave_types: [{ key: 'casual', name: 'Casual' }, { key: 'sick', name: 'Sick' }],
      rows: [
        row({ leave_days: '3.5', leave_by_type: { casual: '2', sick: '1.5' }, lop_days: '1', wfh_days: 2 }),
        row({ leave_days: 4, leave_by_type: { casual: 4 }, optional_holidays: 1, pending_days: '0.5' }),
      ],
    } as SummaryReport
    expect(summaryTotals(report)).toEqual({
      leave_days: 7.5,
      type_0: 6,
      type_1: 1.5,
      lop_days: 1,
      wfh_days: 2,
      optional_holidays: 1,
      pending_days: 0.5,
    })
  })

  it('is all zeros with no report', () => {
    expect(summaryTotals(null)).toEqual({
      leave_days: 0,
      lop_days: 0,
      wfh_days: 0,
      optional_holidays: 0,
      pending_days: 0,
    })
  })
})

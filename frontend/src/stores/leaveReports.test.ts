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

import { approvalParams } from '@/stores/leaveApprovals'
import { reportParams } from '@/stores/leaveReports'
import type { ReportFilters } from '@/types/leaveReports'

const FILTERS: ReportFilters = {
  start: '2026-06-01',
  end: '2026-06-30',
  year: 2026,
  user_id: 'u1',
  department: null,
  office_id: '',
  policy_id: null,
  manager_id: null,
  kind: 'wfh',
  leave_type_id: null,
  status: 'approved',
}

describe('reportParams', () => {
  it('sends each report only the filters it takes, and none that are empty', () => {
    expect(reportParams('summary', FILTERS)).toEqual({
      start: '2026-06-01',
      end: '2026-06-30',
      user_id: 'u1',
    })
    expect(reportParams('register', FILTERS)).toEqual({
      start: '2026-06-01',
      end: '2026-06-30',
      user_id: 'u1',
      kind: 'wfh',
      status: 'approved',
    })
    expect(reportParams('balances', FILTERS)).toEqual({ year: 2026, user_id: 'u1' })
  })
})

describe('approvalParams', () => {
  it('always sends the tab and drops empty filters', () => {
    expect(
      approvalParams('decided', {
        start: '2026-01-01',
        end: '',
        kind: null,
        leave_type_id: 't1',
        user_id: null,
      }),
    ).toEqual({ status: 'decided', start: '2026-01-01', leave_type_id: 't1' })
  })

  it('sends both ends of a range', () => {
    expect(
      approvalParams('pending', {
        start: '2026-03-01',
        end: '2026-03-31',
        kind: 'leave',
        leave_type_id: null,
        user_id: 'u2',
      }),
    ).toEqual({ status: 'pending', start: '2026-03-01', end: '2026-03-31', kind: 'leave', user_id: 'u2' })
  })
})

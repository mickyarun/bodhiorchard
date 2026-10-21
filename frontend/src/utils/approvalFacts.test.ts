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

import type { ApprovalItem, Balance } from '@/types/leave'
import { lastLeaveLine, otherYearBalanceAfter, timeAgo } from '@/utils/approvalFacts'

// Wednesday 21 October 2026, mid-morning local time.
const TODAY = new Date(2026, 9, 21, 10, 30)

describe('timeAgo', () => {
  it.each([
    ['2026-10-21', 'today'],
    ['2026-10-20', 'yesterday'],
    ['2026-10-16', '5 days ago'],
    ['2026-09-02', '7 weeks ago'],
    ['2026-06-01', '4 months ago'],
    ['2024-01-10', '2 years ago'],
  ])('%s → %s', (iso, label) => {
    expect(timeAgo(iso, TODAY)).toBe(label)
  })
})

describe('lastLeaveLine', () => {
  it('names the type, dates, length and how long ago it ended', () => {
    const last = { leave_type: 'Sick leave', start_date: '2026-09-02', end_date: '2026-09-03', days: '2' }
    expect(lastLeaveLine(last, TODAY)).toBe('Sick leave · Wed 2 – Thu 3 Sep · 2 days · 6 weeks ago')
  })

  it('says so when the leave is still running', () => {
    const last = { leave_type: null, start_date: '2026-10-20', end_date: '2026-10-22', days: '3' }
    expect(lastLeaveLine(last, TODAY)).toMatch(/^Leave · .* · 3 days · on leave now$/)
  })
})

function item(balanceAfter: string | null, available: string | null): ApprovalItem {
  const type = { id: 't1', name: 'Casual', code: 'CL', color_key: 'swatch-1' }
  const balance: Balance = {
    leave_type: type, is_paid: true, allocated: '12', adjustments: '0', used: '0', pending: '3', available,
  }
  return {
    request: { leave_type: type } as ApprovalItem['request'],
    route: 'manager', designation: null, department: null, also_out: [],
    balance_after: balanceAfter, balances: [balance], balance_year: 2026, last_leave: null,
  }
}

describe('otherYearBalanceAfter', () => {
  it('stays quiet when the tile already shows the balance after approval', () => {
    expect(otherYearBalanceAfter(item('9', '9'))).toBeNull()
  })

  it('shows the figure when the request is priced on another leave year', () => {
    expect(otherYearBalanceAfter(item('12', '9'))).toBe(12)
  })

  it('has nothing to say for unlimited types', () => {
    expect(otherYearBalanceAfter(item(null, null))).toBeNull()
  })
})

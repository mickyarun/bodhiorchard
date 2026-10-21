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

import type { Balance, CalendarEntry } from '@/types/leave'
import {
  approvalLine,
  balanceCaption,
  codeFromName,
  excludedSummary,
  formatDays,
  formatSignedDays,
  joinWithAnd,
  lopLabel,
  meterPercents,
  requestTypeLabel,
  swatchColor,
  toNumber,
  toNumberOrNull,
} from '@/utils/leave'
import { entriesOnDay } from '@/utils/leaveCalendar'

const casual = { id: 't1', name: 'Casual leave', code: 'CL', color_key: 'swatch-2' }

function balance(overrides: Partial<Balance> = {}): Balance {
  return {
    leave_type: casual,
    is_paid: true,
    accrual: 'upfront',
    allocated: '12.0',
    earned: '12.0',
    adjustments: '0',
    used: '3.0',
    pending: '1.0',
    available: '8.0',
    ...overrides,
  }
}

describe('numbers', () => {
  it('reads decimals sent as strings or numbers', () => {
    expect(toNumber('2.5')).toBe(2.5)
    expect(toNumber(4)).toBe(4)
    expect(toNumber(null)).toBe(0)
    expect(toNumber('not a number')).toBe(0)
    expect(toNumberOrNull(null)).toBeNull()
    expect(toNumberOrNull('1.5')).toBe(1.5)
  })

  it('formats days without trailing zeros', () => {
    expect(formatDays(3)).toBe('3')
    expect(formatDays(2.5)).toBe('2.5')
    expect(formatSignedDays(2)).toBe('+2')
    expect(formatSignedDays(-1.5)).toBe('−1.5')
  })
})

describe('balances', () => {
  it('splits the meter into used and pending', () => {
    expect(meterPercents(balance())).toEqual({ used: 25, pending: (1 / 12) * 100 })
  })

  it('caps the meter at 100 when over-used', () => {
    const over = meterPercents(balance({ used: '14', pending: '2' }))
    expect(over).toEqual({ used: 100, pending: 0 })
  })

  it('counts adjustments in the total', () => {
    expect(balanceCaption(balance({ adjustments: '2' }))).toBe('3 used · 1 pending · of 14')
  })

  it('has no meter or total for unlimited types', () => {
    const unlimited = balance({ allocated: null, available: null, pending: '0' })
    expect(meterPercents(unlimited)).toBeNull()
    expect(balanceCaption(unlimited)).toBe('3 used')
  })
})

describe('labels', () => {
  it('names the request type', () => {
    expect(requestTypeLabel({ kind: 'leave', leave_type: casual })).toBe('Casual leave')
    expect(requestTypeLabel({ kind: 'wfh', leave_type: null })).toBe('Work from home')
    expect(
      requestTypeLabel({ kind: 'optional_holiday', leave_type: null, holiday_name: 'Onam' }),
    ).toBe('Optional holiday · Onam')
  })

  it('joins names with "and"', () => {
    expect(joinWithAnd([])).toBe('')
    expect(joinWithAnd(['A'])).toBe('A')
    expect(joinWithAnd(['A', 'B', 'C'])).toBe('A, B and C')
  })

  it('summarises skipped dates by weekday or holiday name', () => {
    const excluded = [
      { date: '2026-10-24', reason: 'Weekend' },
      { date: '2026-10-25', reason: 'Weekend' },
      { date: '2026-10-20', reason: 'Diwali' },
    ]
    expect(excludedSummary(excluded, [0, 1, 2, 3, 4])).toBe('skips Sat, Sun and Diwali')
    expect(excludedSummary([], [0, 1, 2, 3, 4])).toBe('')
  })

  it('says who approves', () => {
    const base = { auto_approved: false, routes_to_hr: false, approvers: [], problems: [] }
    const priya = [{ user_id: 'u1', name: 'Priya Sharma' }]
    expect(approvalLine({ ...base, approvers: priya }, 'leave', null)).toBe(
      'Goes to Priya Sharma for approval',
    )
    expect(approvalLine({ ...base, routes_to_hr: true }, 'leave', null)).toBe(
      'Goes to HR for approval',
    )
    expect(approvalLine({ ...base, auto_approved: true }, 'wfh', 'auto_within_allowance')).toBe(
      "Approved automatically (within this month's WFH allowance)",
    )
    const nobody = [{ code: 'no_approver', message: 'Nobody can approve this yet' }]
    expect(approvalLine({ ...base, routes_to_hr: true, problems: nobody }, 'leave', null)).toBe('')
  })

  it('derives a code from a type name', () => {
    expect(codeFromName('Casual leave')).toBe('CL')
    expect(codeFromName('Sick')).toBe('SIC')
    expect(codeFromName('  ')).toBe('')
  })

  it('falls back to primary for unknown swatches', () => {
    expect(swatchColor('swatch-2')).toBe('info')
    expect(swatchColor('nope')).toBe('primary')
  })
})

describe('entriesOnDay', () => {
  const entry = (name: string, kind: CalendarEntry['kind']): CalendarEntry => ({
    request_id: name,
    user: { user_id: name, name },
    kind,
    start_date: '2026-10-23',
    end_date: '2026-10-26',
    half_day: 'none',
    status: 'approved',
    is_own: false,
    leave_type: null,
    reason: null,
    working_days: [0, 1, 2, 3, 4],
  })
  const entries = [entry('Zara', 'leave'), entry('Asha', 'wfh'), entry('Bala', 'leave')]

  it('lists leave before WFH, by name', () => {
    expect(entriesOnDay(entries, '2026-10-23').map(e => e.user.name)).toEqual([
      'Bala',
      'Zara',
      'Asha',
    ])
  })

  it("skips each person's own days off, not the viewer's", () => {
    expect(entriesOnDay(entries, '2026-10-24')).toEqual([])
    const sixDay = { ...entry('Ravi', 'leave'), working_days: [0, 1, 2, 3, 4, 5] }
    expect(entriesOnDay([...entries, sixDay], '2026-10-24').map(e => e.user.name)).toEqual([
      'Ravi',
    ])
  })
})

describe('lopLabel', () => {
  it('names loss-of-pay days and stays quiet when there are none', () => {
    expect(lopLabel('2.5')).toBe('2.5 days loss of pay')
    expect(lopLabel(1)).toBe('1 day loss of pay')
    expect(lopLabel('0')).toBe('')
    expect(lopLabel(null)).toBe('')
  })
})

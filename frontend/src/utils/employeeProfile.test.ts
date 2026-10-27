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
import type { Balance } from '@/types/leave'
import {
  formatDayMonth,
  formatFullDate,
  leaveSummary,
  nextAnniversary,
  nextBirthday,
  parseDateOnly,
  profileTabs,
  tenureFor,
  tenureLabel,
} from './employeeProfile'

const TODAY = new Date(2026, 9, 28) // 28 Oct 2026

describe('parseDateOnly', () => {
  it('reads a date-only string as a local date', () => {
    expect(parseDateOnly('2022-01-10')).toEqual(new Date(2022, 0, 10))
  })

  it('returns null for missing or broken values', () => {
    expect(parseDateOnly(null)).toBeNull()
    expect(parseDateOnly('soon')).toBeNull()
  })
})

describe('tenureLabel', () => {
  it('counts years and months', () => {
    expect(tenureLabel('2022-01-10', TODAY)).toBe('4 years 9 months')
  })

  it('only counts a month once its day comes round', () => {
    expect(tenureLabel('2026-07-29', TODAY)).toBe('2 months')
    expect(tenureLabel('2025-10-28', TODAY)).toBe('1 year')
  })

  it('handles a first month and a future start', () => {
    expect(tenureLabel('2026-10-20', TODAY)).toBe('Less than a month')
    expect(tenureLabel('2026-11-03', TODAY)).toBeNull()
    expect(tenureLabel(null, TODAY)).toBeNull()
  })
})

describe('tenureFor', () => {
  const work = { date_of_joining: '2022-01-10', date_of_exit: null, status: 'active' as const }

  it('counts to today while they are here, notice period included', () => {
    expect(tenureFor(work, TODAY)).toBe('4 years 9 months')
    expect(tenureFor({ ...work, status: 'on_notice', date_of_exit: '2026-12-31' }, TODAY)).toBe(
      '4 years 9 months',
    )
  })

  it('stops at the exit date once they have left', () => {
    const exited = { ...work, status: 'exited' as const, date_of_exit: '2024-07-31' }
    expect(tenureFor(exited, TODAY)).toBe('2 years 6 months')
    expect(tenureFor(exited, new Date(2030, 0, 1))).toBe('2 years 6 months')
  })

  it('says nothing for someone who left without an exit date', () => {
    expect(tenureFor({ ...work, status: 'exited' }, TODAY)).toBeNull()
  })
})

describe('nextAnniversary', () => {
  it('finds the next one and how many years it marks', () => {
    expect(nextAnniversary('2022-01-10', TODAY)).toEqual({ date: new Date(2027, 0, 10), years: 5 })
  })

  it('counts today as the anniversary', () => {
    expect(nextAnniversary('2020-10-28', TODAY)).toEqual({ date: new Date(2026, 9, 28), years: 6 })
  })

  it('makes a new joiner wait for their first full year', () => {
    expect(nextAnniversary('2026-10-20', TODAY)).toEqual({ date: new Date(2027, 9, 20), years: 1 })
    expect(nextAnniversary('2026-12-01', TODAY)).toEqual({ date: new Date(2027, 11, 1), years: 1 })
  })

  it('moves 29 Feb to 28 Feb outside leap years', () => {
    expect(nextAnniversary('2024-02-29', TODAY)?.date).toEqual(new Date(2027, 1, 28))
  })

  it('needs a joining date', () => {
    expect(nextAnniversary(null, TODAY)).toBeNull()
  })
})

describe('nextBirthday', () => {
  it('finds the next birthday this year or next', () => {
    expect(nextBirthday('1990-12-02', TODAY)).toEqual(new Date(2026, 11, 2))
    expect(nextBirthday('1990-03-14', TODAY)).toEqual(new Date(2027, 2, 14))
    expect(nextBirthday(null, TODAY)).toBeNull()
  })
})

describe('date labels', () => {
  it('formats full dates and day-month only', () => {
    expect(formatFullDate(new Date(2027, 0, 10))).toBe('10 Jan 2027')
    expect(formatDayMonth(new Date(2027, 2, 14))).toBe('14 Mar')
  })
})

function balance(overrides: Partial<Balance> = {}): Balance {
  return {
    leave_type: { id: 'casual', name: 'Casual leave', code: 'CL', color_key: 'swatch-2' },
    is_paid: true,
    accrual: 'upfront',
    allocated: '12',
    earned: '12',
    adjustments: '0',
    used: '3',
    pending: '0',
    available: '9',
    ...overrides,
  }
}

describe('leaveSummary', () => {
  it('shows days left of the total with the free share as the bar', () => {
    expect(leaveSummary([balance()])).toEqual([
      { key: 'casual', name: 'Casual leave', color: 'swatch-2', left: '9 of 12 left', percent: 75 },
    ])
  })

  it('words a monthly type that is still building up like the Leave tab', () => {
    const [row] = leaveSummary([
      balance({ accrual: 'monthly', allocated: '12', earned: '10', used: '2', available: '8' }),
    ])
    expect(row).toMatchObject({ left: '8 left · 10 earned of 12', percent: 80 })
  })

  it('keeps pending days out of the free share', () => {
    const [row] = leaveSummary([balance({ pending: '3', available: '6' })])
    expect(row.percent).toBe(50)
  })

  it('shows days taken for a type with no limit', () => {
    const [row] = leaveSummary([balance({ allocated: null, earned: null, available: null, used: '1' })])
    expect(row).toMatchObject({ left: '1 day taken', percent: null })
  })

  it('shows an empty bar when nothing is allocated', () => {
    const [row] = leaveSummary([balance({ allocated: '0', earned: '0', used: '0', available: '0' })])
    expect(row).toMatchObject({ left: '0 left', percent: 0 })
  })
})

describe('profileTabs', () => {
  it('always has Employment, and the rest only when allowed', () => {
    const none = { personal: false, leave: false, details: false, documents: false }
    expect(profileTabs(none).map(t => t.value)).toEqual(['employment'])
    const all = { personal: true, leave: true, details: true, documents: true }
    expect(profileTabs(all).map(t => t.value)).toEqual([
      'personal',
      'employment',
      'leave',
      'bank',
      'documents',
    ])
  })

  it('marks Bank and IDs with a lock', () => {
    const tabs = profileTabs({ personal: false, leave: false, details: true, documents: false })
    expect(tabs.find(t => t.value === 'bank')).toEqual({
      value: 'bank',
      label: 'Bank and IDs',
      locked: true,
    })
  })
})

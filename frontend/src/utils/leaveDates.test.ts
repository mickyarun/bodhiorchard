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

import {
  addDays,
  buildMonthGrid,
  formatDayRange,
  formatLeaveYear,
  monthDays,
  parseMonthParam,
  shiftMonth,
  toIsoDate,
  weekdayIndex,
} from '@/utils/leaveDates'

describe('date-only strings', () => {
  it('reads dates as local days', () => {
    expect(toIsoDate(new Date(2026, 9, 20))).toBe('2026-10-20')
    expect(addDays('2026-10-31', 1)).toBe('2026-11-01')
    expect(addDays('2026-03-01', -1)).toBe('2026-02-28')
  })

  it('numbers weekdays from Monday', () => {
    expect(weekdayIndex('2026-10-19')).toBe(0)
    expect(weekdayIndex('2026-10-25')).toBe(6)
  })
})

describe('formatDayRange', () => {
  it('shows a single day', () => {
    expect(formatDayRange('2026-10-20', '2026-10-20')).toBe('Tue 20 Oct')
  })

  it('shares the month when it can', () => {
    expect(formatDayRange('2026-10-19', '2026-10-21')).toBe('Mon 19 – Wed 21 Oct')
  })

  it('names both months across a month boundary', () => {
    expect(formatDayRange('2026-09-30', '2026-10-02')).toBe('Wed 30 Sep – Fri 2 Oct')
  })

  it('adds years across a year boundary', () => {
    expect(formatDayRange('2026-12-31', '2027-01-01')).toBe('Thu 31 Dec 2026 – Fri 1 Jan 2027')
  })
})

describe('formatLeaveYear', () => {
  it('collapses a calendar year', () => {
    expect(formatLeaveYear({ label: 2026, start: '2026-01-01', end: '2026-12-31' })).toBe(
      '1 Jan – 31 Dec 2026',
    )
  })

  it('shows both years for a split leave year', () => {
    expect(formatLeaveYear({ label: 2026, start: '2026-04-01', end: '2027-03-31' })).toBe(
      '1 Apr 2026 – 31 Mar 2027',
    )
  })
})

describe('months', () => {
  const fallback = { year: 2026, month: 10 }

  it('parses the month query param', () => {
    expect(parseMonthParam('2027-02', fallback)).toEqual({ year: 2027, month: 2 })
    expect(parseMonthParam('2027-13', fallback)).toBe(fallback)
    expect(parseMonthParam(undefined, fallback)).toBe(fallback)
  })

  it('moves across year boundaries', () => {
    expect(shiftMonth({ year: 2026, month: 12 }, 1)).toEqual({ year: 2027, month: 1 })
    expect(shiftMonth({ year: 2026, month: 1 }, -1)).toEqual({ year: 2025, month: 12 })
  })

  it('lists every day of the month', () => {
    expect(monthDays({ year: 2028, month: 2 })).toHaveLength(29)
  })

  it('builds Monday-first weeks padded from neighbouring months', () => {
    const grid = buildMonthGrid({ year: 2026, month: 10 })
    expect(grid).toHaveLength(5)
    expect(grid[0][0]).toMatchObject({ iso: '2026-09-28', inMonth: false, weekday: 0 })
    expect(grid[0][3]).toMatchObject({ iso: '2026-10-01', inMonth: true, day: 1 })
    expect(grid[4][6]).toMatchObject({ iso: '2026-11-01', inMonth: false })
  })
})
